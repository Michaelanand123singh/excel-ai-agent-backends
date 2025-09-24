"""
Bulk Excel Part Number Search Parser
Handles user-uploaded Excel files with standardized part number search format
"""

from __future__ import annotations

import io
import pandas as pd
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None


class MatchStatus(Enum):
    FOUND = "found"
    PARTIAL = "partial"
    NOT_FOUND = "not_found"


@dataclass
class UserPartData:
    """Standardized user part data from Excel upload"""
    part_number: str
    part_name: str
    quantity: int
    manufacturer_name: str
    row_index: int  # Original row number for error reporting


@dataclass
class BulkSearchConfig:
    """Configuration for bulk search processing"""
    max_file_size_mb: int = 50
    batch_size: int = 500
    max_results_per_part: int = 3
    required_headers: List[str] = None
    processing_timeout_seconds: int = 30
    enable_manufacturer_cross_check: bool = True
    confidence_threshold: float = 0.3
    
    def __post_init__(self):
        if self.required_headers is None:
            self.required_headers = ["Part Number", "Part name", "Quantity", "Manufacturer name"]


class BulkExcelParser:
    """Parser for bulk Excel part number search files"""
    
    def __init__(self, config: BulkSearchConfig = None):
        self.config = config or BulkSearchConfig()
        
    def validate_headers(self, headers: List[str]) -> Tuple[bool, str, Dict[str, str]]:
        """
        Validate and map Excel headers to standard format.
        Returns: (is_valid, error_message, column_mapping)
        """
        if not headers:
            return False, "No headers found in file", {}
            
        # Normalize headers (trim, case-insensitive)
        normalized_headers = [h.strip().lower() for h in headers]
        required_lower = [h.lower() for h in self.config.required_headers]
        
        # Create mapping from normalized to original headers
        header_mapping = {}
        for orig, norm in zip(headers, normalized_headers):
            header_mapping[norm] = orig
            
        # Check for required headers with flexible matching
        missing_headers = []
        column_mapping = {}
        
        # Flexible header matching
        header_variations = {
            "part number": ["part number", "part_number", "partnumber", "part no", "partno", "pn"],
            "part name": ["part name", "part_name", "partname", "description", "desc", "item name"],
            "quantity": ["quantity", "qty", "amount", "count", "units"],
            "manufacturer name": ["manufacturer name", "manufacturer_name", "manufacturer", "mfg", "brand", "supplier"]
        }
        
        for required_field, variations in header_variations.items():
            found = False
            for variation in variations:
                if variation in normalized_headers:
                    column_mapping[required_field] = header_mapping[variation]
                    found = True
                    break
            if not found:
                missing_headers.append(required_field)
        
        if missing_headers:
            return False, f"Missing required headers: {missing_headers}. Found: {list(header_mapping.keys())}", {}
            
        return True, "", column_mapping
    
    def parse_excel_file(self, file_bytes: bytes, filename: str) -> Tuple[List[UserPartData], List[str]]:
        """
        Parse Excel file and extract user part data.
        Returns: (user_parts, error_messages)
        """
        errors = []
        user_parts = []
        
        try:
            # Detect file format
            if filename.lower().endswith('.csv'):
                df = pd.read_csv(io.BytesIO(file_bytes))
            else:
                # Excel file
                if load_workbook is None:
                    df = pd.read_excel(io.BytesIO(file_bytes), engine='openpyxl')
                else:
                    # Use openpyxl for better performance on large files
                    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
                    ws = wb.worksheets[0]
                    
                    # Convert to DataFrame
                    data = []
                    for row in ws.iter_rows(values_only=True):
                        data.append(row)
                    wb.close()
                    
                    if not data:
                        return [], ["File is empty"]
                    
                    # First row as headers
                    headers = [str(h) if h is not None else f"Column_{i}" for i, h in enumerate(data[0])]
                    df = pd.DataFrame(data[1:], columns=headers)
            
            if df.empty:
                return [], ["File contains no data"]
            
            # Validate headers
            headers = list(df.columns)
            is_valid, error_msg, column_mapping = self.validate_headers(headers)
            
            if not is_valid:
                return [], [error_msg]
            
            # Process each row
            for idx, row in df.iterrows():
                try:
                    # Extract data using column mapping
                    part_number = str(row[column_mapping["part number"]]).strip() if pd.notna(row[column_mapping["part number"]]) else ""
                    part_name = str(row[column_mapping["part name"]]).strip() if pd.notna(row[column_mapping["part name"]]) else ""
                    manufacturer_name = str(row[column_mapping["manufacturer name"]]).strip() if pd.notna(row[column_mapping["manufacturer name"]]) else ""
                    
                    # Parse quantity
                    quantity_raw = row[column_mapping["quantity"]]
                    if pd.isna(quantity_raw):
                        quantity = 0
                    else:
                        try:
                            # Handle various quantity formats
                            if isinstance(quantity_raw, str):
                                quantity_raw = quantity_raw.replace(',', '').strip()
                            quantity = int(float(quantity_raw))
                        except (ValueError, TypeError):
                            quantity = 0
                            errors.append(f"Row {idx + 2}: Invalid quantity '{quantity_raw}', using 0")
                    
                    # Skip rows with empty part number
                    if not part_number or part_number.lower() in ['nan', 'none', '']:
                        errors.append(f"Row {idx + 2}: Empty part number, skipping")
                        continue
                    
                    user_part = UserPartData(
                        part_number=part_number,
                        part_name=part_name,
                        quantity=quantity,
                        manufacturer_name=manufacturer_name,
                        row_index=idx + 2  # +2 for 1-based indexing and header row
                    )
                    user_parts.append(user_part)
                    
                except Exception as e:
                    errors.append(f"Row {idx + 2}: Error processing row - {str(e)}")
                    continue
            
            # Limit to reasonable size
            if len(user_parts) > 50000:  # 50K parts max
                user_parts = user_parts[:50000]
                errors.append(f"File contains {len(user_parts)} parts, limited to 50,000 for performance")
            
            return user_parts, errors
            
        except Exception as e:
            return [], [f"Failed to parse file: {str(e)}"]
    
    def validate_file_size(self, file_bytes: bytes) -> Tuple[bool, str]:
        """Validate file size is within limits"""
        size_mb = len(file_bytes) / (1024 * 1024)
        if size_mb > self.config.max_file_size_mb:
            return False, f"File size {size_mb:.1f}MB exceeds limit of {self.config.max_file_size_mb}MB"
        return True, ""
