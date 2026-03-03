#!/usr/bin/env python3
"""
Simple Transaction Manager for Standalone MongoDB
Provides atomic-like operations without requiring replica sets
"""

import logging
from decimal import Decimal
from contextlib import contextmanager
from pymongo import MongoClient
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)


class SimpleTransactionManager:
    """Simple transaction manager for standalone MongoDB"""
    
    def __init__(self, client: MongoClient):
        self.client = client
        self.operations = []
    
    @contextmanager
    def transaction(self):
        """Simple transaction context (no real transactions for standalone)"""
        try:
            self.operations.clear()
            yield self
        except Exception as e:
            logger.error(f"Operation failed: {e}")
            raise
        finally:
            self.operations.clear()
    
    def update_stock_atomic(self, db, product_id: str, quantity_sold: Decimal) -> bool:
        """Update stock with atomic-like behavior"""
        try:
            products = db["products"]
            
            # First, get the current product to check the stock type
            product = products.find_one({"product_id": product_id})
            if not product:
                raise ValueError(f"Product {product_id} not found")
            
            # Convert stock_quantity to number if it's a string
            current_stock = Decimal(str(product["stock_quantity"]))
            new_stock = current_stock - quantity_sold
            
            if new_stock < 0:
                raise ValueError(f"Insufficient stock. Available: {current_stock}, Required: {quantity_sold}")
            
            # Update with the new stock value as a number
            result = products.update_one(
                {"product_id": product_id},
                {"$set": {"stock_quantity": float(new_stock)}}
            )
            
            if result.modified_count == 0:
                raise ValueError(f"Failed to update stock for {product_id}")
            
            logger.info(f"Stock updated for {product_id}: {current_stock} -> {new_stock}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update stock for {product_id}: {e}")
            return False
    
    def save_receipt_atomic(self, db, receipt_dict: dict) -> str:
        """Save receipt with atomic-like behavior"""
        try:
            # Convert Decimal values to float for MongoDB storage
            def convert_decimals(obj):
                if isinstance(obj, Decimal):
                    return float(obj)
                elif isinstance(obj, dict):
                    return {k: convert_decimals(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_decimals(item) for item in obj]
                return obj
            
            receipt_dict_converted = convert_decimals(receipt_dict)
            
            receipts = db["receipts"]
            result = receipts.insert_one(receipt_dict_converted)
            receipt_id = str(result.inserted_id)
            logger.info(f"Receipt saved with ID: {receipt_id}")
            return receipt_id
        except Exception as e:
            logger.error(f"Failed to save receipt: {e}")
            raise
