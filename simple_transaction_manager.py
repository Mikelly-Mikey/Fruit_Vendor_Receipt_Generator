#!/usr/bin/env python3
"""
Simple Transaction Manager for Standalone MongoDB
Provides atomic-like operations without requiring replica sets
"""

import logging
from decimal import Decimal
from contextlib import contextmanager
from pymongo import MongoClient, ReturnDocument
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
            
            # Get current product and lock with findAndModify
            product = products.find_one_and_update(
                {"product_id": product_id},
                {"$inc": {"stock_quantity": -float(quantity_sold)}},
                return_document=ReturnDocument.BEFORE
            )
            
            if not product:
                raise ValueError(f"Product {product_id} not found")
            
            current_stock = Decimal(str(product["stock_quantity"]))
            
            if current_stock < quantity_sold:
                # Rollback the increment
                products.update_one(
                    {"product_id": product_id},
                    {"$inc": {"stock_quantity": float(quantity_sold)}}
                )
                raise ValueError(f"Insufficient stock. Available: {current_stock}, Required: {quantity_sold}")
            
            logger.info(f"Stock updated {product_id}: {current_stock} -> {current_stock - quantity_sold}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update stock for product {product_id}: {e}")
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


class SimpleSafeCheckoutProcessor:
    """Simple checkout processor for standalone MongoDB"""
    
    def __init__(self, tx_manager: SimpleTransactionManager):
        self.tx_manager = tx_manager
    
    def process_checkout(self, db, cart_items: list, receipt_dict: dict) -> bool:
        """Process checkout with atomic-like behavior"""
        try:
            with self.tx_manager.transaction():
                # Update stock for all items
                for item in cart_items:
                    success = self.tx_manager.update_stock_atomic(
                        db, item.product.product_id, item.quantity
                    )
                    if not success:
                        raise ValueError(f"Failed to update stock for {item.product.name}")
                
                # Save receipt
                receipt_id = self.tx_manager.save_receipt_atomic(db, receipt_dict)
                if not receipt_id:
                    raise ValueError("Failed to save receipt")
                
                logger.info("Checkout completed successfully")
                return True
                
        except Exception as e:
            logger.error(f"Checkout failed: {e}")
            return False
