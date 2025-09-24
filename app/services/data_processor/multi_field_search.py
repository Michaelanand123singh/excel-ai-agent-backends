"""
Multi-field search engine for bulk part number search
Implements intelligent search across Part Number, Part Name, and Manufacturer fields
"""

from __future__ import annotations

import time
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.utils.helpers.part_number import (
    normalize, 
    similarity_score, 
    separator_tokenize,
    PART_NUMBER_CONFIG
)


class MatchType(Enum):
    EXACT_PART_NUMBER = "exact_part_number"
    FUZZY_PART_NUMBER = "fuzzy_part_number"
    PART_NAME_MATCH = "part_name_match"
    MANUFACTURER_MATCH = "manufacturer_match"
    COMBINED_MATCH = "combined_match"


@dataclass
class SearchResult:
    """Result of a single part search"""
    match_status: str  # "found", "partial", "not_found"
    match_type: str
    confidence: float  # 0-100
    database_record: Dict[str, Any]
    price_calculation: Dict[str, Any]
    search_time_ms: float


@dataclass
class BulkSearchResult:
    """Result of bulk search operation"""
    user_data: Dict[str, Any]
    search_result: SearchResult
    processing_errors: List[str]


class MultiFieldSearchEngine:
    """Advanced search engine for multi-field part matching"""
    
    def __init__(self, db: Session, table_name: str):
        self.db = db
        self.table_name = table_name
        self.cache = {}  # Simple in-memory cache for repeated searches
        
    def search_single_part(self, user_part: Dict[str, Any], search_mode: str = "hybrid") -> SearchResult:
        """
        Search for a single part using multi-field strategy
        """
        start_time = time.perf_counter()
        
        part_number = user_part.get("part_number", "").strip()
        part_name = user_part.get("part_name", "").strip()
        manufacturer_name = user_part.get("manufacturer_name", "").strip()
        quantity = user_part.get("quantity", 0)
        
        # Normalize search terms
        part_number_norm = normalize(part_number, 2) if part_number else ""
        part_number_alnum = normalize(part_number, 3) if part_number else ""
        
        # Try different search strategies in order of priority
        search_strategies = [
            self._search_exact_part_number,
            self._search_fuzzy_part_number,
            self._search_part_name,
            self._search_manufacturer,
            self._search_combined_fields
        ]
        
        for strategy in search_strategies:
            try:
                result = strategy(part_number, part_number_norm, part_number_alnum, 
                               part_name, manufacturer_name, quantity, search_mode)
                if result and result.get("match_status") != "not_found":
                    result["search_time_ms"] = (time.perf_counter() - start_time) * 1000
                    return SearchResult(**result)
            except Exception as e:
                # Log error but continue with next strategy
                continue
        
        # No matches found
        return SearchResult(
            match_status="not_found",
            match_type="none",
            confidence=0.0,
            database_record={},
            price_calculation={"unit_price": 0.0, "total_cost": 0.0, "available_quantity": 0},
            search_time_ms=(time.perf_counter() - start_time) * 1000
        )
    
    def _search_exact_part_number(self, part_number: str, part_number_norm: str, 
                                part_number_alnum: str, part_name: str, 
                                manufacturer_name: str, quantity: int, 
                                search_mode: str) -> Optional[Dict[str, Any]]:
        """Exact part number matching with normalization"""
        if not part_number:
            return None
            
        # Multi-format exact search
        sql = f"""
            SELECT 
                "Potential Buyer 1" as company_name,
                "Potential Buyer 1 Contact Details" as contact_details,
                "Potential Buyer 1 email id" as email,
                "Quantity" as available_quantity,
                "Unit_Price",
                "Item_Description",
                "part_number",
                "UQC",
                "Potential Buyer 2" as secondary_buyer
            FROM {self.table_name}
            WHERE 
                LOWER("part_number") = LOWER(:part_number) OR
                LOWER(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE("part_number", '-', ''), '/', ''), ',', ''), '*', ''), '&', ''), '~', ''), '.', ''), '%', '')) = LOWER(:part_number_norm) OR
                LOWER(REGEXP_REPLACE("part_number", '[^a-zA-Z0-9]+', '', 'g')) = LOWER(:part_number_alnum)
            ORDER BY "Unit_Price" ASC
            LIMIT 1
        """
        
        result = self.db.execute(text(sql), {
            "part_number": part_number,
            "part_number_norm": part_number_norm,
            "part_number_alnum": part_number_alnum
        }).fetchone()
        
        if result:
            return self._format_search_result(
                result, "found", "exact_part_number", 100.0, quantity
            )
        return None
    
    def _search_fuzzy_part_number(self, part_number: str, part_number_norm: str, 
                                part_number_alnum: str, part_name: str, 
                                manufacturer_name: str, quantity: int, 
                                search_mode: str) -> Optional[Dict[str, Any]]:
        """Fuzzy part number matching using similarity"""
        if not part_number or search_mode == "exact":
            return None
            
        # Use PostgreSQL trigram similarity if available
        sql = f"""
            SELECT 
                "Potential Buyer 1" as company_name,
                "Potential Buyer 1 Contact Details" as contact_details,
                "Potential Buyer 1 email id" as email,
                "Quantity" as available_quantity,
                "Unit_Price",
                "Item_Description",
                "part_number",
                "UQC",
                "Potential Buyer 2" as secondary_buyer,
                similarity(lower("part_number"), lower(:part_number)) as sim_score
            FROM {self.table_name}
            WHERE similarity(lower("part_number"), lower(:part_number)) >= :min_similarity
            ORDER BY sim_score DESC, "Unit_Price" ASC
            LIMIT 3
        """
        
        try:
            results = self.db.execute(text(sql), {
                "part_number": part_number,
                "min_similarity": PART_NUMBER_CONFIG.get("min_similarity", 0.6)
            }).fetchall()
            
            if results:
                best_result = results[0]
                confidence = float(best_result[9]) * 100  # Convert similarity to percentage
                return self._format_search_result(
                    best_result, "found", "fuzzy_part_number", confidence, quantity
                )
        except Exception:
            # Fallback to Python-side fuzzy matching
            return self._search_fuzzy_python(part_number, part_number_norm, part_number_alnum, quantity)
        
        return None
    
    def _search_fuzzy_python(self, part_number: str, part_number_norm: str, 
                           part_number_alnum: str, quantity: int) -> Optional[Dict[str, Any]]:
        """Python-side fuzzy matching fallback"""
        # Get candidates using ILIKE
        sql = f"""
            SELECT 
                "Potential Buyer 1" as company_name,
                "Potential Buyer 1 Contact Details" as contact_details,
                "Potential Buyer 1 email id" as email,
                "Quantity" as available_quantity,
                "Unit_Price",
                "Item_Description",
                "part_number",
                "UQC",
                "Potential Buyer 2" as secondary_buyer
            FROM {self.table_name}
            WHERE "part_number" ILIKE :pattern
            LIMIT 1000
        """
        
        # Use token-based pattern matching
        tokens = separator_tokenize(part_number)
        if not tokens:
            return None
            
        pattern = f"%{tokens[0]}%"  # Use first token for broad matching
        results = self.db.execute(text(sql), {"pattern": pattern}).fetchall()
        
        if not results:
            return None
        
        # Score results using Python similarity
        best_match = None
        best_score = 0.0
        
        for result in results:
            db_part_number = result[6] or ""
            
            # Calculate similarity across different normalization levels
            scores = [
                similarity_score(part_number.lower(), db_part_number.lower()),
                similarity_score(part_number_norm.lower(), normalize(db_part_number, 2).lower()),
                similarity_score(part_number_alnum.lower(), normalize(db_part_number, 3).lower())
            ]
            
            max_score = max(scores)
            if max_score > best_score and max_score >= PART_NUMBER_CONFIG.get("min_similarity", 0.6):
                best_score = max_score
                best_match = result
        
        if best_match:
            return self._format_search_result(
                best_match, "found", "fuzzy_part_number", best_score * 100, quantity
            )
        
        return None
    
    def _search_part_name(self, part_number: str, part_number_norm: str, 
                         part_number_alnum: str, part_name: str, 
                         manufacturer_name: str, quantity: int, 
                         search_mode: str) -> Optional[Dict[str, Any]]:
        """Search by part name/description"""
        if not part_name:
            return None
            
        sql = f"""
            SELECT 
                "Potential Buyer 1" as company_name,
                "Potential Buyer 1 Contact Details" as contact_details,
                "Potential Buyer 1 email id" as email,
                "Quantity" as available_quantity,
                "Unit_Price",
                "Item_Description",
                "part_number",
                "UQC",
                "Potential Buyer 2" as secondary_buyer
            FROM {self.table_name}
            WHERE "Item_Description" ILIKE :pattern
            ORDER BY "Unit_Price" ASC
            LIMIT 1
        """
        
        # Use first few words of part name for matching
        name_words = part_name.split()[:3]  # First 3 words
        pattern = f"%{'%'.join(name_words)}%"
        
        result = self.db.execute(text(sql), {"pattern": pattern}).fetchone()
        
        if result:
            # Calculate confidence based on name similarity
            db_description = result[5] or ""
            confidence = similarity_score(part_name.lower(), db_description.lower()) * 80  # Max 80% for name match
            
            return self._format_search_result(
                result, "partial", "part_name_match", confidence, quantity
            )
        
        return None
    
    def _search_manufacturer(self, part_number: str, part_number_norm: str, 
                           part_number_alnum: str, part_name: str, 
                           manufacturer_name: str, quantity: int, 
                           search_mode: str) -> Optional[Dict[str, Any]]:
        """Search by manufacturer name"""
        if not manufacturer_name:
            return None
            
        # This would require manufacturer data in the database
        # For now, return None as we don't have manufacturer field in current schema
        return None
    
    def _search_combined_fields(self, part_number: str, part_number_norm: str, 
                              part_number_alnum: str, part_name: str, 
                              manufacturer_name: str, quantity: int, 
                              search_mode: str) -> Optional[Dict[str, Any]]:
        """Combined field search for complex matching"""
        if not part_name:
            return None
            
        # Search using both part number and name
        sql = f"""
            SELECT 
                "Potential Buyer 1" as company_name,
                "Potential Buyer 1 Contact Details" as contact_details,
                "Potential Buyer 1 email id" as email,
                "Quantity" as available_quantity,
                "Unit_Price",
                "Item_Description",
                "part_number",
                "UQC",
                "Potential Buyer 2" as secondary_buyer
            FROM {self.table_name}
            WHERE 
                ("part_number" ILIKE :part_pattern OR "Item_Description" ILIKE :name_pattern)
                AND ("part_number" ILIKE :part_pattern OR "Item_Description" ILIKE :name_pattern)
            ORDER BY "Unit_Price" ASC
            LIMIT 1
        """
        
        part_pattern = f"%{part_number[:5]}%" if part_number else ""
        name_pattern = f"%{part_name[:10]}%" if part_name else ""
        
        if not part_pattern and not name_pattern:
            return None
            
        result = self.db.execute(text(sql), {
            "part_pattern": part_pattern,
            "name_pattern": name_pattern
        }).fetchone()
        
        if result:
            return self._format_search_result(
                result, "partial", "combined_match", 60.0, quantity
            )
        
        return None
    
    def _create_empty_result(self) -> SearchResult:
        """Create empty search result for error cases"""
        return SearchResult(
            match_status="not_found",
            match_type="none",
            confidence=0.0,
            database_record={},
            price_calculation={"unit_price": 0.0, "total_cost": 0.0, "available_quantity": 0},
            search_time_ms=0.0
        )
    
    def _format_search_result(self, db_result: Any, match_status: str, 
                            match_type: str, confidence: float, 
                            requested_quantity: int) -> Dict[str, Any]:
        """Format database result into search result"""
        unit_price = float(db_result[4]) if db_result[4] is not None else 0.0
        available_quantity = int(db_result[3]) if db_result[3] is not None else 0
        total_cost = unit_price * min(requested_quantity, available_quantity)
        
        return {
            "match_status": match_status,
            "match_type": match_type,
            "confidence": confidence,
            "database_record": {
                "company_name": db_result[0] or "N/A",
                "contact_details": db_result[1] or "N/A",
                "email": db_result[2] or "N/A",
                "available_quantity": available_quantity,
                "unit_price": unit_price,
                "item_description": db_result[5] or "N/A",
                "part_number": db_result[6] or "N/A",
                "uqc": db_result[7] or "N/A",
                "secondary_buyer": db_result[8] or "N/A"
            },
            "price_calculation": {
                "unit_price": unit_price,
                "total_cost": total_cost,
                "available_quantity": available_quantity,
                "requested_quantity": requested_quantity
            }
        }
