"""
Advanced Confidence Calculator for Part Number Matching
Provides comprehensive confidence scoring for search results
"""

from typing import Dict, Any, List, Tuple
import re
from difflib import SequenceMatcher

from app.utils.helpers.part_number import (
    normalize, 
    similarity_score, 
    separator_tokenize,
    levenshtein
)


class ConfidenceCalculator:
    """Advanced confidence calculator for part number matching"""
    
    def __init__(self):
        self.config = {
            "exact_match_bonus": 20,  # Bonus for exact matches
            "case_insensitive_bonus": 10,  # Bonus for case-insensitive exact match
            "normalized_bonus": 15,  # Bonus for normalized exact match
            "similarity_threshold": 0.1,  # Lower threshold to include more matches
            "description_weight": 0.4,  # Increased weight for description matching
            "part_number_weight": 0.6,  # Slightly reduced weight for part number matching
            "manufacturer_weight": 0.2,  # Weight for manufacturer matching
            "length_penalty_factor": 0.05,  # Reduced penalty for length differences
        }
    
    def calculate_confidence(self, 
                           search_part: str, 
                           search_name: str,
                           search_manufacturer: str,
                           db_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate comprehensive confidence score for a database record
        
        Args:
            search_part: Part number being searched
            search_name: Part name being searched  
            search_manufacturer: Manufacturer being searched
            db_record: Database record to score
            
        Returns:
            Dict containing confidence score and breakdown
        """
        db_part = db_record.get("part_number", "")
        db_description = db_record.get("item_description", "")
        db_manufacturer = db_record.get("manufacturer", "")
        
        # Calculate individual scores
        part_number_score = self._calculate_part_number_confidence(search_part, db_part)
        description_score = self._calculate_description_confidence(search_name, db_description)
        manufacturer_score = self._calculate_manufacturer_confidence(search_manufacturer, db_manufacturer)
        
        # Calculate weighted overall score
        overall_score = (
            part_number_score["score"] * self.config["part_number_weight"] +
            description_score["score"] * self.config["description_weight"] +
            manufacturer_score["score"] * self.config["manufacturer_weight"]
        )
        
        # Apply length penalty if significant difference
        length_penalty = self._calculate_length_penalty(search_part, db_part)
        final_score = max(0, overall_score - length_penalty)
        
        # Determine match type
        match_type = self._determine_match_type(part_number_score, description_score, manufacturer_score)
        
        # Determine match status
        match_status = self._determine_match_status(final_score, part_number_score["score"])
        
        return {
            "confidence": round(final_score, 2),
            "match_type": match_type,
            "match_status": match_status,
            "breakdown": {
                "part_number": part_number_score,
                "description": description_score,
                "manufacturer": manufacturer_score,
                "length_penalty": length_penalty
            }
        }
    
    def _calculate_part_number_confidence(self, search_part: str, db_part: str) -> Dict[str, Any]:
        """Calculate confidence based on part number matching"""
        if not search_part or not db_part:
            return {"score": 0, "method": "no_data", "details": "Missing part numbers"}
        
        search_norm = search_part.strip().lower()
        db_norm = db_part.strip().lower()
        
        # Exact match (case-insensitive)
        if search_norm == db_norm:
            return {
                "score": 100,
                "method": "exact_match",
                "details": f"Exact match: '{search_part}' = '{db_part}'"
            }
        
        # Normalized exact match
        search_normalized = normalize(search_part, 2)
        db_normalized = normalize(db_part, 2)
        if search_normalized.lower() == db_normalized.lower():
            return {
                "score": 95,
                "method": "normalized_exact",
                "details": f"Normalized exact match: '{search_normalized}' = '{db_normalized}'"
            }
        
        # Alphanumeric exact match
        search_alnum = normalize(search_part, 3)
        db_alnum = normalize(db_part, 3)
        if search_alnum.lower() == db_alnum.lower():
            return {
                "score": 90,
                "method": "alnum_exact",
                "details": f"Alphanumeric exact match: '{search_alnum}' = '{db_alnum}'"
            }
        
        # Similarity-based scoring
        similarities = [
            similarity_score(search_part.lower(), db_part.lower()),
            similarity_score(search_normalized.lower(), db_normalized.lower()),
            similarity_score(search_alnum.lower(), db_alnum.lower())
        ]
        
        max_similarity = max(similarities)
        if max_similarity >= self.config["similarity_threshold"]:
            score = max_similarity * 100
            return {
                "score": round(score, 2),
                "method": "similarity",
                "details": f"Similarity match: {max_similarity:.3f} (methods: original, normalized, alnum)"
            }
        
        # Levenshtein distance scoring
        lev_distance = levenshtein(search_part.lower(), db_part.lower())
        max_len = max(len(search_part), len(db_part))
        if max_len > 0:
            lev_similarity = 1 - (lev_distance / max_len)
            if lev_similarity >= self.config["similarity_threshold"]:
                score = lev_similarity * 100
                return {
                    "score": round(score, 2),
                    "method": "levenshtein",
                    "details": f"Levenshtein similarity: {lev_similarity:.3f} (distance: {lev_distance})"
                }
        
        # Token overlap scoring
        search_tokens = set(separator_tokenize(search_part))
        db_tokens = set(separator_tokenize(db_part))
        if search_tokens and db_tokens:
            overlap = len(search_tokens.intersection(db_tokens))
            union = len(search_tokens.union(db_tokens))
            token_similarity = overlap / union if union > 0 else 0
            
            if token_similarity >= self.config["similarity_threshold"]:
                score = token_similarity * 100
                return {
                    "score": round(score, 2),
                    "method": "token_overlap",
                    "details": f"Token overlap: {token_similarity:.3f} ({overlap}/{union} tokens)"
                }
        
        return {
            "score": 0,
            "method": "no_match",
            "details": f"No significant similarity found between '{search_part}' and '{db_part}'"
        }
    
    def _calculate_description_confidence(self, search_name: str, db_description: str) -> Dict[str, Any]:
        """Calculate confidence based on description/part name matching"""
        if not search_name or not db_description:
            return {"score": 0, "method": "no_data", "details": "Missing descriptions"}
        
        search_norm = search_name.strip().lower()
        db_norm = db_description.strip().lower()
        
        # Exact match
        if search_norm == db_norm:
            return {
                "score": 80,
                "method": "exact_description",
                "details": f"Exact description match: '{search_name}' = '{db_description}'"
            }
        
        # Contains match
        if search_norm in db_norm or db_norm in search_norm:
            return {
                "score": 70,
                "method": "contains_match",
                "details": f"Description contains match: '{search_name}' in '{db_description}'"
            }
        
        # Word overlap
        search_words = set(search_norm.split())
        db_words = set(db_norm.split())
        if search_words and db_words:
            overlap = len(search_words.intersection(db_words))
            union = len(search_words.union(db_words))
            word_similarity = overlap / union if union > 0 else 0
            
            if word_similarity >= 0.3:  # Lower threshold for descriptions
                score = word_similarity * 60  # Max 60% for description matches
                return {
                    "score": round(score, 2),
                    "method": "word_overlap",
                    "details": f"Word overlap: {word_similarity:.3f} ({overlap}/{union} words)"
                }
        
        # Similarity scoring
        similarity = similarity_score(search_norm, db_norm)
        if similarity >= 0.3:
            score = similarity * 60
            return {
                "score": round(score, 2),
                "method": "description_similarity",
                "details": f"Description similarity: {similarity:.3f}"
            }
        
        return {
            "score": 0,
            "method": "no_description_match",
            "details": f"No significant description similarity between '{search_name}' and '{db_description}'"
        }
    
    def _calculate_manufacturer_confidence(self, search_manufacturer: str, db_manufacturer: str) -> Dict[str, Any]:
        """Calculate confidence based on manufacturer matching"""
        if not search_manufacturer or not db_manufacturer:
            return {"score": 0, "method": "no_data", "details": "Missing manufacturer data"}
        
        search_norm = search_manufacturer.strip().lower()
        db_norm = db_manufacturer.strip().lower()
        
        # Exact match
        if search_norm == db_norm:
            return {
                "score": 50,
                "method": "exact_manufacturer",
                "details": f"Exact manufacturer match: '{search_manufacturer}' = '{db_manufacturer}'"
            }
        
        # Contains match
        if search_norm in db_norm or db_norm in search_norm:
            return {
                "score": 40,
                "method": "contains_manufacturer",
                "details": f"Manufacturer contains match: '{search_manufacturer}' in '{db_manufacturer}'"
            }
        
        # Similarity scoring
        similarity = similarity_score(search_norm, db_norm)
        if similarity >= 0.5:  # Higher threshold for manufacturer
            score = similarity * 50
            return {
                "score": round(score, 2),
                "method": "manufacturer_similarity",
                "details": f"Manufacturer similarity: {similarity:.3f}"
            }
        
        return {
            "score": 0,
            "method": "no_manufacturer_match",
            "details": f"No significant manufacturer similarity between '{search_manufacturer}' and '{db_manufacturer}'"
        }
    
    def _calculate_length_penalty(self, search_part: str, db_part: str) -> float:
        """Calculate penalty for significant length differences"""
        if not search_part or not db_part:
            return 0
        
        len_diff = abs(len(search_part) - len(db_part))
        max_len = max(len(search_part), len(db_part))
        
        if max_len == 0:
            return 0
        
        length_ratio = len_diff / max_len
        if length_ratio > 0.5:  # More than 50% length difference
            return length_ratio * 20  # Up to 20 point penalty
        
        return 0
    
    def _determine_match_type(self, part_score: Dict, desc_score: Dict, mfg_score: Dict) -> str:
        """Determine the type of match based on scores"""
        if part_score["score"] >= 90:
            return "exact_part_number"
        elif part_score["score"] >= 70:
            return "fuzzy_part_number"
        elif desc_score["score"] >= 50:
            return "description_match"
        elif mfg_score["score"] >= 30:
            return "manufacturer_match"
        elif part_score["score"] >= 30 or desc_score["score"] >= 30:
            return "partial_match"
        else:
            return "no_match"
    
    def _determine_match_status(self, overall_score: float, part_score: float) -> str:
        """Determine match status based on overall and part number scores"""
        if overall_score >= 70:  # Lowered threshold for "found"
            return "found"
        elif overall_score >= 0.1 or part_score >= 0.1:  # Much lower threshold for "partial"
            return "partial"
        else:
            return "not_found"


# Global instance
confidence_calculator = ConfidenceCalculator()
