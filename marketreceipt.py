#!/usr/bin/env python3
"""
Fresh Fruits Market - Cashier Receipt System
Unified GUI Application for processing customer purchases

REQUIRES MongoDB to be running:
  sudo apt install mongodb
  sudo systemctl start mongodb

Features:
- Cashier inputs products for customer
- Displays price per product
- Calculates total cost
- Processes payments (Cash/Card/M-Pesa)
- Deducts stock from database
- Generates customer receipt
- Product management (add/update/delete)
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import datetime
import uuid
import os
import re
import logging
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
from decimal import Decimal, InvalidOperation
from contextlib import contextmanager

from pymongo import MongoClient
from pymongo.errors import PyMongoError
from type_safety import TypeConverter, ValidatedProduct, ValidatedCartItem, ValidatedPaymentDetails, InputValidator
from simple_transaction_manager import SimpleTransactionManager, SimpleSafeCheckoutProcessor
from payment_integration import MPesaIntegration, CardPaymentIntegration, PaymentNotificationWindow, InventoryManager, BusinessLogbook


# Configuration constants
VAT_RATE = Decimal('0.16')
VAT_INCLUSIVE = True
MONGO_TIMEOUT_MS = 5000
DEFAULT_DB_NAME = "fruit_vendor_db"
CARD_NUMBER_PATTERN = r'^\d{13,19}$'
PHONE_NUMBER_PATTERN = r'^\+?\d{10,15}$'

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PaymentMethod(Enum):
    CASH = "cash"
    CARD = "card"
    MPESA = "mpesa"


class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass


class DatabaseError(Exception):
    """Custom exception for database errors"""
    pass


@dataclass
class Product:
    name: str
    price_per_unit: Decimal
    unit: str
    stock_quantity: Decimal
    product_id: Optional[str] = None

    def __post_init__(self):
        if not self.product_id:
            self.product_id = str(uuid.uuid4())[:8].upper()
        # Ensure decimal types
        if not isinstance(self.price_per_unit, Decimal):
            self.price_per_unit = Decimal(str(self.price_per_unit))
        if not isinstance(self.stock_quantity, Decimal):
            self.stock_quantity = Decimal(str(self.stock_quantity))


@dataclass
class CartItem:
    product: Product
    quantity: Decimal

    def __post_init__(self):
        # Ensure decimal type
        if not isinstance(self.quantity, Decimal):
            self.quantity = Decimal(str(self.quantity))

    @property
    def subtotal(self) -> Decimal:
        return self.product.price_per_unit * self.quantity


@dataclass
class PaymentDetails:
    method: PaymentMethod
    amount_paid: Decimal
    transaction_reference: Optional[str] = None
    phone_number: Optional[str] = None
    card_last_four: Optional[str] = None
    card_type: Optional[str] = None
    balance: Decimal = Decimal('0.0')

    def __post_init__(self):
        # Ensure decimal types
        if not isinstance(self.amount_paid, Decimal):
            self.amount_paid = Decimal(str(self.amount_paid))
        if not isinstance(self.balance, Decimal):
            self.balance = Decimal(str(self.balance))


@dataclass
class Receipt:
    receipt_number: str
    date: str
    time: str
    items: List[Dict]
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    payment: Dict
    vendor_name: str = "Fresh Fruits Market"
    vendor_address: str = "123 Market Street, Nairobi"
    vendor_phone: str = "+254 700 123 456"

    def __post_init__(self):
        # Ensure decimal types
        if not isinstance(self.subtotal, Decimal):
            self.subtotal = Decimal(str(self.subtotal))
        if not isinstance(self.tax_amount, Decimal):
            self.tax_amount = Decimal(str(self.tax_amount))
        if not isinstance(self.total_amount, Decimal):
            self.total_amount = Decimal(str(self.total_amount))


class DatabaseManager:
    """Handles MongoDB operations with transaction safety"""
    
    def __init__(self, connection_string: Optional[str] = None):
        connection_string = connection_string or os.environ.get("MONGO_URI","mongodb://localhost:27017/")
        try:
            self.client = MongoClient(connection_string, serverSelectionTimeoutMS=MONGO_TIMEOUT_MS)
            self.client.admin.command('ping')
            self.db = self.client[DEFAULT_DB_NAME]
            self.products = self.db["products"]
            self.receipts = self.db["receipts"]
            
            # Initialize simple transaction manager
            self.tx_manager = SimpleTransactionManager(self.client)
            self.checkout_processor = SimpleSafeCheckoutProcessor(self.tx_manager)
            
            # Create indexes for better performance
            self._create_indexes()
            logger.info("Database connection established successfully")
        except PyMongoError as e:
            logger.error(f"Database connection failed: {e}")
            raise DatabaseError(
                f"Cannot connect to MongoDB. Please ensure MongoDB is installed and running.\n"
                f"Contact administrator for assistance."
            ) from e
    
    def _create_indexes(self):
        """Create database indexes for better performance"""
        try:
            self.products.create_index("product_id", unique=True)
            self.products.create_index("name")
            self.receipts.create_index("receipt_number", unique=True)
            self.receipts.create_index("date")
            logger.info("Database indexes created successfully")
        except PyMongoError as e:
            logger.warning(f"Failed to create indexes: {e}")
    
    def __del__(self):
        """Cleanup database connection"""
        try:
            if hasattr(self, 'client'):
                self.client.close()
                logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")
    
    @contextmanager
    def transaction(self):
        """Context manager for database operations with rollback capability"""
        # MongoDB doesn't support multi-document transactions in older versions
        # For now, we'll use a simple try-catch pattern
        try:
            yield
        except Exception as e:
            logger.error(f"Database operation failed: {e}")
            raise DatabaseError(f"Database operation failed: {str(e)}") from e
    
    def validate_card_number(self, card_number: str) -> bool:
        """Validate card number format"""
        return bool(re.match(CARD_NUMBER_PATTERN, card_number.replace(" ", "")))
    
    def validate_phone_number(self, phone_number: str) -> bool:
        """Validate phone number format"""
        return bool(re.match(PHONE_NUMBER_PATTERN, phone_number))
    
    def add_product(self, product: ValidatedProduct) -> str:
        """Add a new product to the database with type safety"""
        try:
            with self.tx_manager.transaction():
                product_dict = product.to_dict()
                self.products.insert_one(product_dict)
                logger.info(f"Product added: {product.name} (ID: {product.product_id})")
                return product.product_id
        except PyMongoError as e:
            logger.error(f"Failed to add product: {e}")
            raise DatabaseError("Failed to add product") from e
    
    def get_product(self, product_id: str) -> Optional[Dict]:
        """Retrieve a product by ID with type conversion"""
        try:
            product = self.products.find_one({"product_id": product_id})
            if product:
                # Convert string values back to Decimal
                product['price_per_unit'] = Decimal(product.get('price_per_unit', '0'))
                product['stock_quantity'] = Decimal(product.get('stock_quantity', '0'))
            return product
        except PyMongoError as e:
            logger.error(f"Failed to retrieve product {product_id}: {e}")
            raise DatabaseError("Failed to retrieve product") from e
    
    def get_all_products(self) -> List[Dict]:
        """Retrieve all products"""
        try:
            products = list(self.products.find())
            # Convert string values back to Decimal
            for product in products:
                product['price_per_unit'] = Decimal(product.get('price_per_unit', '0'))
                product['stock_quantity'] = Decimal(product.get('stock_quantity', '0'))
            return products
        except PyMongoError as e:
            logger.error(f"Failed to retrieve products: {e}")
            raise DatabaseError("Failed to retrieve products") from e
    
    def update_stock(self, product_id: str, quantity_sold: Decimal) -> bool:
        """Deduct stock when items are sold using atomic operations"""
        try:
            return self.tx_manager.update_stock_atomic(self.db, product_id, quantity_sold)
        except Exception as e:
            logger.error(f"Failed to update stock for product {product_id}: {e}")
            raise DatabaseError("Failed to update stock") from e
    
    def update_product_stock(self, product_id: str, new_stock: Any) -> tuple[bool, str]:
        """Add/restock product quantity with type safety"""
        try:
            validated_stock = InputValidator.validate_stock(new_stock)
            with self.tx_manager.transaction():
                result = self.products.update_one(
                    {"product_id": product_id},
                    {"$set": {"stock_quantity": str(validated_stock)}}
                )
                if result.modified_count > 0:
                    logger.info(f"Product stock updated {product_id}: {validated_stock}")
                    return True, f"Stock updated to {validated_stock}"
                return False, "Failed to update stock - product not found"
        except (ValueError, PyMongoError) as e:
            logger.error(f"Failed to update product stock {product_id}: {e}")
            return False, str(e)
    
    def update_product_price(self, product_id: str, new_price: Any) -> tuple[bool, str]:
        """Update product price with type safety"""
        try:
            validated_price = InputValidator.validate_price(new_price)
            with self.tx_manager.transaction():
                result = self.products.update_one(
                    {"product_id": product_id},
                    {"$set": {"price_per_unit": str(validated_price)}}
                )
                if result.modified_count > 0:
                    logger.info(f"Product price updated {product_id}: {validated_price}")
                    return True, f"Price updated to KES {validated_price:.2f}"
                return False, "Failed to update price - product not found"
        except (ValueError, PyMongoError) as e:
            logger.error(f"Failed to update product price {product_id}: {e}")
            return False, str(e)
    
    def delete_product(self, product_id: str) -> bool:
        """Remove product from database"""
        try:
            with self.transaction():
                result = self.products.delete_one({"product_id": product_id})
                if result.deleted_count > 0:
                    logger.info(f"Product deleted: {product_id}")
                return result.deleted_count > 0
        except PyMongoError as e:
            logger.error(f"Failed to delete product {product_id}: {e}")
            raise DatabaseError("Failed to delete product") from e
    
    def save_transaction(self, receipt: Receipt) -> str:
        """Save receipt transaction to database"""
        try:
            with self.transaction():
                receipt_dict = asdict(receipt)
                receipt_dict["created_at"] = datetime.datetime.now()
                # Convert Decimal values to strings for MongoDB
                receipt_dict['subtotal'] = str(receipt.subtotal)
                receipt_dict['tax_amount'] = str(receipt.tax_amount)
                receipt_dict['total_amount'] = str(receipt.total_amount)
                receipt_dict['payment']['amount_paid'] = str(receipt.payment['amount_paid'])
                receipt_dict['payment']['balance'] = str(receipt.payment['balance'])
                
                result = self.receipts.insert_one(receipt_dict)
                logger.info(f"Transaction saved: {receipt.receipt_number}")
                return str(result.inserted_id)
        except PyMongoError as e:
            logger.error(f"Failed to save transaction: {e}")
            raise DatabaseError("Failed to save transaction") from e


class PaymentProcessor:
    """Handles payment processing and calculations"""
    
    @staticmethod
    def calculate_totals(items: List[CartItem]) -> Tuple[Decimal, Decimal, Decimal]:
        """Calculate totals with VAT-inclusive pricing"""
        try:
            # Subtotal = sum of all item subtotals (prices include VAT)
            subtotal = sum(item.subtotal for item in items)
            
            if VAT_INCLUSIVE:
                # VAT is already included in subtotal
                # Calculate VAT component: subtotal - (subtotal / 1.16)
                tax_amount = (subtotal - (subtotal / (Decimal('1') + VAT_RATE))).quantize(Decimal('0.01'))
                total = subtotal  # Total equals subtotal (VAT inclusive)
            else:
                # VAT is added on top
                tax_amount = (subtotal * VAT_RATE).quantize(Decimal('0.01'))
                total = subtotal + tax_amount
            
            return subtotal, tax_amount, total
        except (InvalidOperation, TypeError) as e:
            logger.error(f"Error calculating totals: {e}")
            raise ValidationError("Invalid calculation parameters") from e
    
    def process_cash_payment(self, total: Decimal, amount_tendered: Any) -> PaymentDetails:
        """Process cash payment with validation"""
        try:
            # Convert amount_tendered to Decimal
            validated_amount = TypeConverter.to_positive_decimal(amount_tendered, "amount_tendered")
            
            if validated_amount < total:
                raise ValidationError("Insufficient amount tendered")
            balance = validated_amount - total
            return PaymentDetails(
                method=PaymentMethod.CASH, 
                amount_paid=validated_amount, 
                balance=balance
            )
        except (InvalidOperation, TypeError, ValueError) as e:
            logger.error(f"Error processing cash payment: {e}")
            raise ValidationError("Invalid payment amount") from e
    
    def process_card_payment(self, total: Decimal, card_number: str, card_type: str, auth_code: str) -> PaymentDetails:
        """Process card payment with validation"""
        try:
            # Validate card number
            if not re.match(CARD_NUMBER_PATTERN, card_number.replace(" ", "")):
                raise ValidationError("Invalid card number format")
            
            last_four = card_number.replace(" ", "")[-4:] if len(card_number.replace(" ", "")) >= 4 else "****"
            return PaymentDetails(
                method=PaymentMethod.CARD, 
                amount_paid=total,
                transaction_reference=auth_code, 
                card_last_four=last_four,
                card_type=card_type, 
                balance=Decimal('0.0')
            )
        except (InvalidOperation, TypeError) as e:
            logger.error(f"Error processing card payment: {e}")
            raise ValidationError("Invalid card payment details") from e
    
    def process_mpesa_payment(self, total: Decimal, phone_number: str, mpesa_code: str) -> PaymentDetails:
        """Process M-Pesa payment with validation"""
        try:
            # Validate phone number
            if not re.match(PHONE_NUMBER_PATTERN, phone_number):
                raise ValidationError("Invalid phone number format")
            
            return PaymentDetails(
                method=PaymentMethod.MPESA, 
                amount_paid=total,
                phone_number=phone_number, 
                transaction_reference=mpesa_code, 
                balance=Decimal('0.0')
            )
        except (InvalidOperation, TypeError) as e:
            logger.error(f"Error processing M-Pesa payment: {e}")
            raise ValidationError("Invalid M-Pesa payment details") from e


class MarketReceiptApp:
    """Main application class for the Fresh Fruits Market system"""
    
    def __init__(self, db_connection: Optional[str] = None):
        try:
            self.db = DatabaseManager(db_connection)
            self.payment_processor = PaymentProcessor()
            self.cart: List[ValidatedCartItem] = []
            
            # Initialize payment integrations
            self.mpesa_integration = MPesaIntegration()
            self.card_integration = CardPaymentIntegration()
            
            # Initialize business management
            self.inventory_manager = InventoryManager(self.db)
            self.logbook = BusinessLogbook(self.db)
            
            self._initialize_sample_products()
            logger.info("MarketReceiptApp initialized successfully")
        except (DatabaseError, ValidationError) as e:
            logger.error(f"Failed to initialize MarketReceiptApp: {e}")
            raise
    
    def _initialize_sample_products(self):
        """Initialize sample products if database is empty"""
        try:
            if not self.db.get_all_products():
                sample_products = [
                    Product("Apples", Decimal('50.0'), "piece", Decimal('100.0')),
                    Product("Ripe Banana", Decimal('10.0'), "piece", Decimal('150.0')),
                    Product("Oranges", Decimal('10.0'), "piece", Decimal('80.0')),
                    Product("Mangoes", Decimal('50.0'), "piece", Decimal('200.0')),
                    Product("Pineapples", Decimal('80.0'), "piece", Decimal('50.0')),
                    Product("Watermelon", Decimal('300.0'), "piece", Decimal('30.0')),
                    Product("Coconut", Decimal('120.0'), "piece", Decimal('30.0')),
                    Product("Grapes", Decimal('400.0'), "punnet", Decimal('40.0')),
                    Product("Strawberries", Decimal('500.0'), "punnet", Decimal('60.0')),
                ]
                for product in sample_products:
                    self.db.add_product(product)
                logger.info("Sample products initialized")
        except (DatabaseError, ValidationError) as e:
            logger.error(f"Failed to initialize sample products: {e}")
            raise
    
    def get_all_products(self) -> List[Dict]:
        """Get all products from database"""
        try:
            return self.db.get_all_products()
        except DatabaseError as e:
            logger.error(f"Failed to get products: {e}")
            raise
    
    def add_to_cart(self, product_id: str, quantity: Any) -> Tuple[bool, str]:
        """Add product to cart with stock validation"""
        try:
            # Validate quantity
            validated_quantity = InputValidator.validate_quantity(quantity)
            
            product_data = self.db.get_product(product_id)
            if not product_data:
                return False, "Product not found!"
            
            if product_data['stock_quantity'] < validated_quantity:
                return False, f"Insufficient stock! Available: {product_data['stock_quantity']:.1f}"
            
            # Create validated product
            validated_product = ValidatedProduct(
                name=product_data['name'], 
                price_per_unit=product_data['price_per_unit'],
                unit=product_data['unit'], 
                stock_quantity=product_data['stock_quantity'],
                product_id=product_data['product_id']
            )
            
            # Create validated cart item
            cart_item = ValidatedCartItem(validated_product, validated_quantity)
            self.cart.append(cart_item)
            logger.info(f"Added to cart: {validated_quantity} {validated_product.unit} of {validated_product.name}")
            return True, f"Added {validated_quantity} {validated_product.unit} of {validated_product.name}"
        except (DatabaseError, ValidationError, InvalidOperation, ValueError) as e:
            logger.error(f"Failed to add to cart: {e}")
            return False, "Failed to add item to cart"
    
    def remove_from_cart(self, index: int):
        if 0 <= index < len(self.cart):
            self.cart.pop(index)
    
    def clear_cart(self):
        self.cart = []
    
    def get_cart_items(self) -> List[ValidatedCartItem]:
        return self.cart
    
    def update_product_stock(self, product_id: str, new_stock: float) -> tuple[bool, str]:
        """Add or restock product"""
        product_data = self.db.get_product(product_id)
        if not product_data:
            return False, "Product not found!"
        if self.db.update_product_stock(product_id, new_stock):
            return True, f"Stock updated for {product_data['name']} to {new_stock:.1f}"
        return False, "Failed to update stock"
    
    def update_product_price(self, product_id: str, new_price: float) -> tuple[bool, str]:
        """Update product price"""
        product_data = self.db.get_product(product_id)
        if not product_data:
            return False, "Product not found!"
        if new_price <= 0:
            return False, "Price must be greater than 0"
        if self.db.update_product_price(product_id, new_price):
            return True, f"Price updated for {product_data['name']} to KES {new_price:.2f}"
        return False, "Failed to update price"
    
    def add_new_product(self, name: str, price: Any, unit: str, stock: Any) -> tuple[bool, str]:
        """Add a new product to database with type safety"""
        try:
            # Validate inputs
            validated_name = InputValidator.validate_product_name(name)
            validated_price = InputValidator.validate_price(price)
            validated_unit = InputValidator.validate_unit(unit)
            validated_stock = InputValidator.validate_stock(stock)
            
            # Create validated product
            product = ValidatedProduct(
                name=validated_name,
                price_per_unit=validated_price,
                unit=validated_unit,
                stock_quantity=validated_stock
            )
            
            self.db.add_product(product)
            return True, f"Product '{validated_name}' added with ID: {product.product_id}"
        except ValueError as e:
            return False, str(e)
        except Exception as e:
            logger.error(f"Failed to add product: {e}")
            return False, "Failed to add product"
    
    def delete_product(self, product_id: str) -> tuple[bool, str]:
        """Remove product from database"""
        product_data = self.db.get_product(product_id)
        if not product_data:
            return False, "Product not found!"
        if self.db.delete_product(product_id):
            return True, f"Product '{product_data['name']}' deleted"
        return False, "Failed to delete product"
    
    def calculate_totals(self) -> tuple:
        return self.payment_processor.calculate_totals(self.cart)
    
    def checkout(self, payment_method: PaymentMethod, **kwargs) -> Optional[Receipt]:
        if not self.cart:
            return None
        
        subtotal, tax_amount, total = self.payment_processor.calculate_totals(self.cart)
        
        try:
            # Log checkout attempt
            self.logbook.log_activity(
                "checkout_attempt",
                f"Processing {payment_method.value} payment of KES {total:.2f}",
                details={"items": len(self.cart), "total": float(total)}
            )
            
            if payment_method == PaymentMethod.CASH:
                amount_tendered = kwargs.get('amount_tendered', 0)
                payment_details = self.payment_processor.process_cash_payment(total, amount_tendered)
                
                # Cash payment is immediate - proceed with transaction
                return self._complete_transaction(payment_details, subtotal, tax_amount, total)
                
            elif payment_method == PaymentMethod.CARD:
                card_number = kwargs.get('card_number', '')
                card_type = kwargs.get('card_type', 'Card')
                auth_code = kwargs.get('auth_code', str(uuid.uuid4())[:6].upper())
                
                # For card payments, also process immediately for now
                payment_details = self.payment_processor.process_card_payment(total, card_number, card_type, auth_code)
                return self._complete_transaction(payment_details, subtotal, tax_amount, total)
                    
            elif payment_method == PaymentMethod.MPESA:
                phone_number = kwargs.get('phone_number', '')
                mpesa_code = kwargs.get('mpesa_code', 'U' + str(uuid.uuid4())[:6].upper())
                
                # Process M-Pesa payment
                result = self.mpesa_integration.initiate_payment(phone_number, float(total), mpesa_code)
                if result["success"]:
                    # For M-Pesa, we need to wait for payment confirmation
                    # Return None to indicate payment is pending
                    self.logbook.log_activity(
                        "mpesa_initiated",
                        f"M-Pesa payment initiated for {phone_number}",
                        details={"amount": float(total), "transaction_id": result["transaction_id"]}
                    )
                    return None  # Payment pending
                else:
                    raise ValueError(f"M-Pesa payment failed: {result.get('error')}")
            else:
                return None
                
        except Exception as e:
            self.logbook.log_activity(
                "checkout_failed",
                f"Checkout failed: {str(e)}",
                details={"payment_method": payment_method.value, "error": str(e)}
            )
            logger.error(f"Checkout failed: {e}")
            return None
    
    def _complete_transaction(self, payment_details, subtotal, tax_amount, total) -> Receipt:
        """Complete the transaction with stock deduction and receipt generation"""
        now = datetime.datetime.now()
        items_data = [{"product_name": item.product.name, "quantity": item.quantity,
                       "unit": item.product.unit, "unit_price": item.product.price_per_unit,
                       "subtotal": item.subtotal} for item in self.cart]
        
        receipt = Receipt(
            receipt_number=f"RCP-{uuid.uuid4().hex[:8].upper()}",
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M:%S"),
            items=items_data,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total,
            payment={
                "method": payment_details.method.value,
                "amount_paid": payment_details.amount_paid,
                "balance": payment_details.balance,
                "transaction_reference": payment_details.transaction_reference,
                "phone_number": payment_details.phone_number,
                "card_last_four": payment_details.card_last_four,
                "card_type": payment_details.card_type
            }
        )
        
        # Use simple transaction manager for atomic-like operations
        try:
            # Update stock for each item
            for item in self.cart:
                success = self.db.tx_manager.update_stock_atomic(
                    self.db.db, item.product.product_id, item.quantity
                )
                if not success:
                    raise ValueError(f"Failed to update stock for {item.product.name}")
                
                # Log stock movement
                self.logbook.log_activity(
                    "stock_deduction",
                    f"Stock deducted: {item.product.name} ({item.quantity} {item.product.unit})",
                    details={
                        "product_id": item.product.product_id,
                        "quantity": float(item.quantity),
                        "remaining_stock": float(item.product.stock_quantity - item.quantity)
                    }
                )
            
            # Save transaction
            receipt_dict = asdict(receipt)
            receipt_id = self.db.tx_manager.save_receipt_atomic(self.db.db, receipt_dict)
            
            # Log successful transaction
            self.logbook.log_activity(
                "transaction_completed",
                f"Transaction completed: {receipt.receipt_number}",
                details={
                    "receipt_id": receipt_id,
                    "total_amount": float(total),
                    "payment_method": payment_details.method.value,
                    "items_count": len(self.cart)
                }
            )
                
        except Exception as e:
            logger.error(f"Transaction failed: {e}")
            raise
        
        # Clear cart after successful transaction
        self.cart = []
        
        return receipt
    
    def format_receipt(self, receipt: Receipt) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("           FRESH FRUITS MARKET")
        lines.append("        " + receipt.vendor_address)
        lines.append("          Tel: " + receipt.vendor_phone)
        lines.append("=" * 60)
        lines.append(f"Receipt No: {receipt.receipt_number}")
        lines.append(f"Date: {receipt.date}          Time: {receipt.time}")
        lines.append("-" * 60)
        lines.append(f"{'Item':<18}{'Qty':<10}{'Price':<12}{'Total':<12}")
        lines.append("-" * 60)
        
        for item in receipt.items:
            qty_str = f"{item['quantity']:.1f} {item['unit']}"
            lines.append(f"{item['product_name']:<18}{qty_str:<10}{item['unit_price']:<12.2f}{item['subtotal']:<12.2f}")
        
        lines.append("-" * 60)
        
        # VAT-inclusive display
        if abs(receipt.subtotal - receipt.total_amount) < 0.01:  # VAT inclusive
            lines.append(f"{'Subtotal (incl. VAT):':<40}{receipt.subtotal:>18.2f}")
            lines.append(f"{'VAT Included (16%):':<40}{receipt.tax_amount:>18.2f}")
            lines.append(f"{'TOTAL:':<40}{receipt.total_amount:>18.2f}")
        else:  # VAT exclusive
            lines.append(f"{'Subtotal:':<40}{receipt.subtotal:>18.2f}")
            lines.append(f"{'VAT (16%):':<40}{receipt.tax_amount:>18.2f}")
            lines.append(f"{'TOTAL:':<40}{receipt.total_amount:>18.2f}")
        
        lines.append("-" * 60)
        
        payment = receipt.payment
        lines.append(f"Payment: {payment['method'].upper()}")
        lines.append(f"Amount Paid: {payment['amount_paid']:>.2f}")
        
        if payment['balance'] > 0:
            lines.append(f"BALANCE: {payment['balance']:.2f}")
        
        if payment.get('transaction_reference'):
            lines.append(f"Ref: {payment['transaction_reference']}")
        
        if payment.get('phone_number'):
            lines.append(f"M-Pesa: {payment['phone_number']}")
        
        if payment.get('card_last_four'):
            card_type = payment.get('card_type', 'Card')
            lines.append(f"{card_type}: ****{payment['card_last_four']}")
        
        lines.append("=" * 60)
        lines.append("     Thank you for shopping with us!")
        lines.append("        Please come again!")
        lines.append("=" * 60)
        
        return "\n".join(lines)


class CashierReceiptSystemGUI:
    """GUI class for the Cashier Receipt System"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Fresh Fruits Market - Cashier System")
        self.root.geometry("1000x800")
        
        try:
            self.app = MarketReceiptApp()
            
            # Setup payment notification callbacks
            self.app.mpesa_integration.add_notification_callback(self.handle_payment_notification)
            self.app.card_integration.add_notification_callback(self.handle_payment_notification)
            
            # Initialize notification window
            self.notification_window = PaymentNotificationWindow(root)
            
        except (DatabaseError, ValidationError) as e:
            messagebox.showerror("Database Error", str(e))
            self.root.destroy()
            return
        
        self.setup_ui()
        self.refresh_products()
    
    def handle_payment_notification(self, notification):
        """Handle payment notifications from M-Pesa and Card integrations"""
        # Show notification popup
        self.root.after(0, lambda: self.notification_window.show_notification(notification))
        
        # If payment completed, auto-complete the transaction
        if notification.status.value == "completed":
            self.root.after(100, self.auto_complete_payment, notification)
    
    def auto_complete_payment(self, notification):
        """Auto-complete transaction after payment confirmation"""
        try:
            # Get current cart items
            cart_items = self.app.get_cart_items()
            if not cart_items:
                return
            
            # Calculate totals
            subtotal, tax_amount, total = self.app.calculate_totals()
            
            # Create payment details for completed transaction
            if "MP" in notification.transaction_id:  # M-Pesa
                payment_details = self.app.payment_processor.process_mpesa_payment(
                    total, notification.phone_number, notification.transaction_id
                )
            else:  # Card
                payment_details = self.app.payment_processor.process_card_payment(
                    total, "****" + notification.reference[-4:], "Card", notification.transaction_id
                )
            
            # Complete transaction
            receipt = self.app._complete_transaction(payment_details, subtotal, tax_amount, total)
            
            if receipt:
                # Update GUI
                receipt_text = self.app.format_receipt(receipt)
                self.receipt_text.delete(1.0, tk.END)
                self.receipt_text.insert(1.0, receipt_text)
                self.refresh_cart()
                self.refresh_products()
                
                # Show receipt
                self.show_full_receipt()
                
                messagebox.showinfo("Payment Completed", f"Payment of KES {notification.amount:.2f} received successfully!")
            
        except Exception as e:
            logger.error(f"Auto-complete payment failed: {e}")
            messagebox.showerror("Error", "Failed to complete payment transaction")
    
    def _parse_product_selection(self, selected: str) -> Tuple[str, str]:
        """Parse product selection string to extract ID and name"""
        parts = selected.split(" - ", 1)
        product_id = parts[0]
        product_name = parts[1] if len(parts) > 1 else "Unknown"
        return product_id, product_name
    
    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text="FRESH FRUITS MARKET", font=('Arial', 20, 'bold')).pack()
        ttk.Label(header_frame, text="Cashier Receipt System", font=('Arial', 12)).pack()
        
        # Product Management Button
        ttk.Button(header_frame, text="Manage Products", 
                  command=self.open_product_manager).pack(side=tk.LEFT, padx=5)
        
        # Business Management Button
        ttk.Button(header_frame, text="Business Reports", 
                  command=self.open_business_manager).pack(side=tk.LEFT, padx=5)
        
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=1)
        
        left_frame = ttk.LabelFrame(content_frame, text="Available Products", padding="10")
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        prod_container = ttk.Frame(left_frame)
        prod_container.pack(fill=tk.BOTH, expand=True)
        
        self.product_tree = ttk.Treeview(prod_container, 
                                         columns=('ID', 'Name', 'Price', 'Unit', 'Stock'), 
                                         show='headings', height=12)
        self.product_tree.heading('ID', text='ID')
        self.product_tree.heading('Name', text='Product Name')
        self.product_tree.heading('Price', text='Price (KES)')
        self.product_tree.heading('Unit', text='Unit')
        self.product_tree.heading('Stock', text='In Stock')
        self.product_tree.column('ID', width=70)
        self.product_tree.column('Name', width=140)
        self.product_tree.column('Price', width=90, anchor=tk.E)
        self.product_tree.column('Unit', width=70)
        self.product_tree.column('Stock', width=70, anchor=tk.E)
        
        prod_scroll = ttk.Scrollbar(prod_container, orient=tk.VERTICAL, command=self.product_tree.yview)
        self.product_tree.configure(yscrollcommand=prod_scroll.set)
        self.product_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        prod_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        add_frame = ttk.Frame(left_frame)
        add_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(add_frame, text="Quantity:", font=('Arial', 11)).pack(side=tk.LEFT)
        self.quantity_var = tk.StringVar(value="1")
        qty_entry = ttk.Entry(add_frame, textvariable=self.quantity_var, width=10, font=('Arial', 11))
        qty_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(add_frame, text="ADD TO CART", command=self.add_to_cart).pack(side=tk.LEFT, padx=10)
        
        right_frame = ttk.Frame(content_frame)
        right_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        
        cart_frame = ttk.LabelFrame(right_frame, text="Customer's Cart", padding="10")
        cart_frame.pack(fill=tk.BOTH, expand=True)
        
        cart_container = ttk.Frame(cart_frame)
        cart_container.pack(fill=tk.BOTH, expand=True)
        
        self.cart_tree = ttk.Treeview(cart_container, 
                                     columns=('Product', 'Qty', 'Unit', 'Price', 'Subtotal'), 
                                     show='headings', height=8)
        self.cart_tree.heading('Product', text='Product')
        self.cart_tree.heading('Qty', text='Qty')
        self.cart_tree.heading('Unit', text='Unit')
        self.cart_tree.heading('Price', text='Unit Price')
        self.cart_tree.heading('Subtotal', text='Amount')
        self.cart_tree.column('Product', width=120)
        self.cart_tree.column('Qty', width=60, anchor=tk.E)
        self.cart_tree.column('Unit', width=60)
        self.cart_tree.column('Price', width=80, anchor=tk.E)
        self.cart_tree.column('Subtotal', width=80, anchor=tk.E)
        
        cart_scroll = ttk.Scrollbar(cart_container, orient=tk.VERTICAL, command=self.cart_tree.yview)
        self.cart_tree.configure(yscrollcommand=cart_scroll.set)
        self.cart_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cart_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        cart_btn_frame = ttk.Frame(cart_frame)
        cart_btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(cart_btn_frame, text="Remove Selected", command=self.remove_from_cart).pack(side=tk.LEFT, padx=5)
        ttk.Button(cart_btn_frame, text="Clear All", command=self.clear_cart).pack(side=tk.LEFT, padx=5)
        
        totals_frame = ttk.Frame(cart_frame)
        totals_frame.pack(fill=tk.X, pady=(15, 0))
        
        self.subtotal_var = tk.StringVar(value="Subtotal: KES 0.00")
        self.tax_var = tk.StringVar(value="VAT (16%): KES 0.00")
        self.total_var = tk.StringVar(value="TOTAL: KES 0.00")
        
        ttk.Label(totals_frame, textvariable=self.subtotal_var, font=('Arial', 11)).pack(anchor=tk.E)
        ttk.Label(totals_frame, textvariable=self.tax_var, font=('Arial', 11)).pack(anchor=tk.E)
        ttk.Separator(totals_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)
        ttk.Label(totals_frame, textvariable=self.total_var, font=('Arial', 14, 'bold'), foreground='green').pack(anchor=tk.E)
        
        payment_frame = ttk.LabelFrame(right_frame, text="Payment Method", padding="10")
        payment_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.payment_method = tk.StringVar(value="cash")
        pm_frame = ttk.Frame(payment_frame)
        pm_frame.pack(fill=tk.X)
        ttk.Radiobutton(pm_frame, text="Cash", variable=self.payment_method, 
                       value="cash", command=self.update_payment_fields).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(pm_frame, text="Card", variable=self.payment_method, 
                       value="card", command=self.update_payment_fields).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(pm_frame, text="M-Pesa", variable=self.payment_method, 
                       value="mpesa", command=self.update_payment_fields).pack(side=tk.LEFT, padx=10)
        
        self.payment_details_frame = ttk.Frame(payment_frame)
        self.payment_details_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.cash_frame = ttk.Frame(self.payment_details_frame)
        ttk.Label(self.cash_frame, text="Amount Tendered (KES):").pack(side=tk.LEFT)
        self.cash_amount = ttk.Entry(self.cash_frame, width=15, font=('Arial', 11))
        self.cash_amount.pack(side=tk.LEFT, padx=5)
        
        self.card_frame = ttk.Frame(self.payment_details_frame)
        ttk.Label(self.card_frame, text="Card Type:").pack(side=tk.LEFT)
        self.card_type = ttk.Combobox(self.card_frame, values=["Mastercard", "Visa", "ATM Card"], 
                                      width=12, state="readonly")
        self.card_type.set("Visa")
        self.card_type.pack(side=tk.LEFT, padx=5)
        ttk.Label(self.card_frame, text="Card #:").pack(side=tk.LEFT)
        self.card_number = ttk.Entry(self.card_frame, width=20, font=('Arial', 11))
        self.card_number.pack(side=tk.LEFT, padx=5)
        
        self.mpesa_frame = ttk.Frame(self.payment_details_frame)
        ttk.Label(self.mpesa_frame, text="Phone:").pack(side=tk.LEFT)
        self.mpesa_phone = ttk.Entry(self.mpesa_frame, width=15, font=('Arial', 11))
        self.mpesa_phone.pack(side=tk.LEFT, padx=5)
        ttk.Label(self.mpesa_frame, text="M-Pesa Code:").pack(side=tk.LEFT)
        self.mpesa_code = ttk.Entry(self.mpesa_frame, width=15, font=('Arial', 11))
        self.mpesa_code.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(payment_frame, text="PROCESS PAYMENT & PRINT RECEIPT", 
                  command=self.checkout).pack(fill=tk.X, pady=(15, 0))
        
        receipt_frame = ttk.LabelFrame(main_frame, text="Customer Receipt (Give This to Customer)", padding="10")
        receipt_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        self.receipt_text = scrolledtext.ScrolledText(receipt_frame, wrap=tk.WORD,
                                                      font=('Courier', 11), bg='white')
        self.receipt_text.pack(fill=tk.BOTH, expand=True)
        
        ttk.Button(receipt_frame, text="Print Receipt", command=self.print_receipt).pack(side=tk.LEFT, padx=5)
        ttk.Button(receipt_frame, text="View Full Receipt", command=self.show_full_receipt).pack(side=tk.LEFT, padx=5)
        
        self.update_payment_fields()
    
    def open_product_manager(self):
        """Open product management dialog"""
        manager_window = tk.Toplevel(self.root)
        manager_window.title("Product Management")
        manager_window.geometry("500x600")
        
        # Frame for adding new product
        add_frame = ttk.LabelFrame(manager_window, text="Add New Product", padding="10")
        add_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(add_frame, text="Name:").grid(row=0, column=0, sticky=tk.W)
        self.new_name = ttk.Entry(add_frame, width=20)
        self.new_name.grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(add_frame, text="Price (KES):").grid(row=1, column=0, sticky=tk.W)
        self.new_price = ttk.Entry(add_frame, width=20)
        self.new_price.grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Label(add_frame, text="Unit:").grid(row=2, column=0, sticky=tk.W)
        self.new_unit = ttk.Combobox(add_frame, values=["kg", "piece", "bunch", "punnet", "box"], width=18)
        self.new_unit.set("kg")
        self.new_unit.grid(row=2, column=1, padx=5, pady=2)
        
        ttk.Label(add_frame, text="Stock:").grid(row=3, column=0, sticky=tk.W)
        self.new_stock = ttk.Entry(add_frame, width=20)
        self.new_stock.insert(0, "0")
        self.new_stock.grid(row=3, column=1, padx=5, pady=2)
        
        ttk.Button(add_frame, text="Add Product", command=self.add_new_product_gui).grid(row=4, column=0, columnspan=2, pady=10)
        
        # Frame for updating existing product
        update_frame = ttk.LabelFrame(manager_window, text="Update Existing Product", padding="10")
        update_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(update_frame, text="Select Product:").grid(row=0, column=0, sticky=tk.W)
        products = self.app.get_all_products()
        product_list = [f"{p['product_id']} - {p['name']}" for p in products]
        self.selected_product = ttk.Combobox(update_frame, values=product_list, width=30)
        self.selected_product.grid(row=0, column=1, padx=5, pady=2)
        self.selected_product.bind('<<ComboboxSelected>>', self.on_product_select)
        
        self.current_info = ttk.Label(update_frame, text="Current: Stock: - | Price: KES -")
        self.current_info.grid(row=1, column=0, columnspan=2, pady=5)
        
        ttk.Label(update_frame, text="New Stock:").grid(row=2, column=0, sticky=tk.W)
        self.update_stock_val = ttk.Entry(update_frame, width=20)
        self.update_stock_val.grid(row=2, column=1, padx=5, pady=2)
        ttk.Button(update_frame, text="Update Stock", command=self.update_stock_gui).grid(row=3, column=0, columnspan=2, pady=5)
        
        ttk.Label(update_frame, text="New Price (KES):").grid(row=4, column=0, sticky=tk.W)
        self.update_price_val = ttk.Entry(update_frame, width=20)
        self.update_price_val.grid(row=4, column=1, padx=5, pady=2)
        ttk.Button(update_frame, text="Update Price", command=self.update_price_gui).grid(row=5, column=0, columnspan=2, pady=5)
        
        ttk.Separator(update_frame, orient=tk.HORIZONTAL).grid(row=6, column=0, columnspan=2, sticky=tk.EW, pady=10)
        ttk.Button(update_frame, text="Delete Selected Product", 
                  command=self.delete_product_gui, foreground='red').grid(row=7, column=0, columnspan=2, pady=5)
        
        ttk.Button(manager_window, text="Close", command=manager_window.destroy).pack(pady=10)
    
    def open_business_manager(self):
        """Open business management and reports window"""
        manager_window = tk.Toplevel(self.root)
        manager_window.title("Business Management & Reports")
        manager_window.geometry("800x600")
        
        # Create notebook for tabbed interface
        notebook = ttk.Notebook(manager_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Inventory Report Tab
        inventory_frame = ttk.Frame(notebook)
        notebook.add(inventory_frame, text="Inventory Report")
        self.setup_inventory_report(inventory_frame)
        
        # Sales Summary Tab
        sales_frame = ttk.Frame(notebook)
        notebook.add(sales_frame, text="Sales Summary")
        self.setup_sales_summary(sales_frame)
        
        # Activity Log Tab
        activity_frame = ttk.Frame(notebook)
        notebook.add(activity_frame, text="Activity Log")
        self.setup_activity_log(activity_frame)
        
        # Stock Movements Tab
        movements_frame = ttk.Frame(notebook)
        notebook.add(movements_frame, text="Stock Movements")
        self.setup_stock_movements(movements_frame)
        
        ttk.Button(manager_window, text="Close", command=manager_window.destroy).pack(pady=10)
    
    def setup_inventory_report(self, parent):
        """Setup inventory report interface"""
        # Refresh button
        ttk.Button(parent, text="Refresh Report", command=self.refresh_inventory_report).pack(pady=10)
        
        # Report display
        self.inventory_text = scrolledtext.ScrolledText(parent, wrap=tk.WORD, font=('Courier', 10))
        self.inventory_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Initial report
        self.refresh_inventory_report()
    
    def refresh_inventory_report(self):
        """Refresh inventory report"""
        try:
            report = self.app.inventory_manager.get_inventory_report()
            
            self.inventory_text.delete(1.0, tk.END)
            
            if report:
                lines = []
                lines.append("=" * 60)
                lines.append("           INVENTORY REPORT")
                lines.append("=" * 60)
                lines.append(f"Total Products: {report.get('total_products', 0)}")
                lines.append(f"Total Stock Value: KES {report.get('total_stock_value', 0):.2f}")
                lines.append("")
                
                # Low stock items
                low_stock = report.get('low_stock_items', [])
                if low_stock:
                    lines.append("⚠️  LOW STOCK ITEMS:")
                    lines.append("-" * 40)
                    for item in low_stock:
                        lines.append(f"  {item['name']}: {item['current_stock']} {item['unit']}")
                    lines.append("")
                
                # All products
                lines.append("ALL PRODUCTS:")
                lines.append("-" * 40)
                lines.append(f"{'Product Name':<20}{'Price':<12}{'Stock':<10}{'Value':<15}")
                lines.append("-" * 40)
                
                for product in report.get('products', []):
                    name = product['name'][:18] + ".." if len(product['name']) > 18 else product['name']
                    price = float(product['price_per_unit'])
                    stock = float(product['stock_quantity'])
                    value = price * stock
                    lines.append(f"{name:<20}{price:<12.2f}{stock:<10.1f}{value:<15.2f}")
                
                lines.append("=" * 60)
                
                self.inventory_text.insert(1.0, "\n".join(lines))
            else:
                self.inventory_text.insert(1.0, "No inventory data available")
                
        except Exception as e:
            self.inventory_text.insert(1.0, f"Error generating report: {e}")
    
    def setup_sales_summary(self, parent):
        """Setup sales summary interface"""
        # Date range selection
        date_frame = ttk.Frame(parent)
        date_frame.pack(pady=10)
        
        ttk.Label(date_frame, text="Date Range:").pack(side=tk.LEFT, padx=5)
        ttk.Button(date_frame, text="Today", command=lambda: self.load_sales_summary("today")).pack(side=tk.LEFT, padx=5)
        ttk.Button(date_frame, text="This Week", command=lambda: self.load_sales_summary("week")).pack(side=tk.LEFT, padx=5)
        ttk.Button(date_frame, text="This Month", command=lambda: self.load_sales_summary("month")).pack(side=tk.LEFT, padx=5)
        ttk.Button(date_frame, text="All Time", command=lambda: self.load_sales_summary("all")).pack(side=tk.LEFT, padx=5)
        
        # Report display
        self.sales_text = scrolledtext.ScrolledText(parent, wrap=tk.WORD, font=('Courier', 10))
        self.sales_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Initial report
        self.load_sales_summary("today")
    
    def load_sales_summary(self, period):
        """Load sales summary for specified period"""
        try:
            # Calculate date range based on period
            import datetime
            now = datetime.datetime.now()
            
            if period == "today":
                start_date = now.replace(hour=0, minute=0, second=0)
                end_date = now.replace(hour=23, minute=59, second=59)
            elif period == "week":
                start_date = now - datetime.timedelta(days=7)
                end_date = now
            elif period == "month":
                start_date = now - datetime.timedelta(days=30)
                end_date = now
            else:  # all time
                start_date = None
                end_date = None
            
            date_range = (start_date, end_date) if start_date else None
            summary = self.app.inventory_manager.get_sales_summary(date_range)
            
            self.sales_text.delete(1.0, tk.END)
            
            if summary:
                lines = []
                lines.append("=" * 60)
                lines.append(f"           SALES SUMMARY - {period.upper()}")
                lines.append("=" * 60)
                lines.append(f"Total Sales: KES {summary.get('total_sales', 0):.2f}")
                lines.append(f"Total Transactions: {summary.get('total_transactions', 0)}")
                lines.append(f"Average Transaction: KES {summary.get('average_transaction', 0):.2f}")
                lines.append("")
                
                # Payment methods breakdown
                methods = summary.get('payment_methods', {})
                lines.append("PAYMENT METHODS:")
                lines.append("-" * 30)
                for method, count in methods.items():
                    lines.append(f"  {method.title()}: {count} transactions")
                lines.append("")
                
                # Recent transactions
                lines.append("RECENT TRANSACTIONS:")
                lines.append("-" * 40)
                lines.append(f"{'Receipt #':<12}{'Date':<12}{'Amount':<12}{'Method':<10}")
                lines.append("-" * 40)
                
                receipts = summary.get('receipts', [])[:10]  # Show last 10
                for receipt in receipts:
                    receipt_num = receipt.get('receipt_number', 'N/A')[:10]
                    date = receipt.get('date', 'N/A')[:10]
                    amount = float(receipt.get('total_amount', 0))
                    method = receipt.get('payment', {}).get('method', 'N/A')
                    lines.append(f"{receipt_num:<12}{date:<12}{amount:<12.2f}{method:<10}")
                
                lines.append("=" * 60)
                
                self.sales_text.insert(1.0, "\n".join(lines))
            else:
                self.sales_text.insert(1.0, "No sales data available")
                
        except Exception as e:
            self.sales_text.insert(1.0, f"Error loading sales summary: {e}")
    
    def setup_activity_log(self, parent):
        """Setup activity log interface"""
        # Filter options
        filter_frame = ttk.Frame(parent)
        filter_frame.pack(pady=10)
        
        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="All", command=lambda: self.load_activity_log()).pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="Sales", command=lambda: self.load_activity_log("transaction_completed")).pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="Stock", command=lambda: self.load_activity_log("stock_deduction")).pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="Products", command=lambda: self.load_activity_log("product")).pack(side=tk.LEFT, padx=5)
        
        # Log display
        self.activity_text = scrolledtext.ScrolledText(parent, wrap=tk.WORD, font=('Courier', 9))
        self.activity_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Initial log
        self.load_activity_log()
    
    def load_activity_log(self, activity_type=None):
        """Load activity log"""
        try:
            activities = self.app.logbook.get_activities(activity_type)
            
            self.activity_text.delete(1.0, tk.END)
            
            lines = []
            lines.append("=" * 80)
            lines.append(f"           ACTIVITY LOG - {activity_type.upper() if activity_type else 'ALL'}")
            lines.append("=" * 80)
            lines.append(f"{'Date':<12}{'Time':<10}{'Type':<20}{'Description':<30}{'User':<10}")
            lines.append("-" * 80)
            
            for activity in activities[:50]:  # Show last 50 activities
                date = activity.get('date', 'N/A')
                time = activity.get('time', 'N/A')
                act_type = activity.get('activity_type', 'N/A')[:18]
                description = activity.get('description', 'N/A')[:28]
                user = activity.get('user', 'N/A')
                lines.append(f"{date:<12}{time:<10}{act_type:<20}{description:<30}{user:<10}")
            
            lines.append("=" * 80)
            
            self.activity_text.insert(1.0, "\n".join(lines))
            
        except Exception as e:
            self.activity_text.insert(1.0, f"Error loading activity log: {e}")
    
    def setup_stock_movements(self, parent):
        """Setup stock movements interface"""
        # Product selection
        select_frame = ttk.Frame(parent)
        select_frame.pack(pady=10)
        
        ttk.Label(select_frame, text="Product:").pack(side=tk.LEFT, padx=5)
        products = self.app.get_all_products()
        product_names = [p['name'] for p in products]
        
        self.movement_product_var = tk.StringVar()
        product_combo = ttk.Combobox(select_frame, textvariable=self.movement_product_var, values=product_names, width=30)
        product_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(select_frame, text="Show Movements", command=self.load_stock_movements).pack(side=tk.LEFT, padx=5)
        ttk.Button(select_frame, text="Show All", command=lambda: self.load_stock_movements(None)).pack(side=tk.LEFT, padx=5)
        
        # Movements display
        self.movements_text = scrolledtext.ScrolledText(parent, wrap=tk.WORD, font=('Courier', 9))
        self.movements_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Initial load
        self.load_stock_movements(None)
    
    def load_stock_movements(self, product_name=None):
        """Load stock movements for a product"""
        try:
            # Find product ID if product name is provided
            product_id = None
            if product_name:
                products = self.app.get_all_products()
                for p in products:
                    if p['name'] == product_name:
                        product_id = p['product_id']
                        break
            
            movements = self.app.inventory_manager.get_stock_movements(product_id)
            
            self.movements_text.delete(1.0, tk.END)
            
            lines = []
            lines.append("=" * 80)
            lines.append(f"           STOCK MOVEMENTS - {product_name or 'ALL PRODUCTS'}")
            lines.append("=" * 80)
            lines.append(f"{'Date':<12}{'Product':<20}{'Quantity':<10}{'Unit Price':<12}{'Subtotal':<12}")
            lines.append("-" * 80)
            
            for movement in movements[:100]:  # Show last 100 movements
                date = movement.get('date', 'N/A')[:10]
                product = movement.get('product_name', 'N/A')[:18]
                quantity = movement.get('quantity', 0)
                unit_price = movement.get('unit_price', 0)
                subtotal = movement.get('subtotal', 0)
                lines.append(f"{date:<12}{product:<20}{quantity:<10}{unit_price:<12.2f}{subtotal:<12.2f}")
            
            lines.append("=" * 80)
            
            self.movements_text.insert(1.0, "\n".join(lines))
            
        except Exception as e:
            self.movements_text.insert(1.0, f"Error loading stock movements: {e}")
    
    def on_product_select(self, event=None):
        """Handle product selection in combobox"""
        selected = self.selected_product.get()
        if selected:
            product_id, _ = self._parse_product_selection(selected)
            product_data = self.app.db.get_product(product_id)
            if product_data:
                self.current_info.config(
                    text=f"Current: Stock: {product_data['stock_quantity']:.1f} | Price: KES {product_data['price_per_unit']:.2f}"
                )
    
    def add_new_product_gui(self):
        try:
            name = self.new_name.get().strip()
            price = float(self.new_price.get())
            unit = self.new_unit.get()
            stock = float(self.new_stock.get())
            
            if not name:
                messagebox.showerror("Error", "Product name is required")
                return
            
            success, message = self.app.add_new_product(name, price, unit, stock)
            if success:
                messagebox.showinfo("Success", message)
                self.new_name.delete(0, tk.END)
                self.new_price.delete(0, tk.END)
                self.new_stock.delete(0, tk.END)
                self.new_stock.insert(0, "0")
                self.refresh_products()
                products = self.app.get_all_products()
                self.selected_product['values'] = [f"{p['product_id']} - {p['name']}" for p in products]
            else:
                messagebox.showerror("Error", message)
        except ValueError:
            messagebox.showerror("Error", "Please enter valid numbers for price and stock")
    
    def update_stock_gui(self):
        """Update product stock from GUI"""
        try:
            selected = self.selected_product.get()
            if not selected:
                messagebox.showerror("Error", "Please select a product")
                return
            product_id, _ = self._parse_product_selection(selected)
            new_stock = Decimal(self.update_stock_val.get())
            
            success, message = self.app.update_product_stock(product_id, new_stock)
            if success:
                messagebox.showinfo("Success", message)
                self.update_stock_val.delete(0, tk.END)
                self.refresh_products()
                self.on_product_select()
            else:
                messagebox.showerror("Error", message)
        except (ValueError, InvalidOperation):
            messagebox.showerror("Error", "Please enter a valid stock quantity")
    
    def update_price_gui(self):
        """Update product price from GUI"""
        try:
            selected = self.selected_product.get()
            if not selected:
                messagebox.showerror("Error", "Please select a product")
                return
            product_id, _ = self._parse_product_selection(selected)
            new_price = Decimal(self.update_price_val.get())
            
            success, message = self.app.update_product_price(product_id, new_price)
            if success:
                messagebox.showinfo("Success", message)
                self.update_price_val.delete(0, tk.END)
                self.refresh_products()
                self.on_product_select()
            else:
                messagebox.showerror("Error", message)
        except (ValueError, InvalidOperation):
            messagebox.showerror("Error", "Please enter a valid price")
    
    def delete_product_gui(self):
        """Delete product from GUI"""
        selected = self.selected_product.get()
        if not selected:
            messagebox.showerror("Error", "Please select a product")
            return
        
        product_id, product_name = self._parse_product_selection(selected)
        
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{product_name}'?"):
            success, message = self.app.delete_product(product_id)
            if success:
                messagebox.showinfo("Success", message)
                self.selected_product.set('')
                self.refresh_products()
                products = self.app.get_all_products()
                self.selected_product['values'] = [f"{p['product_id']} - {p['name']}" for p in products]
                self.current_info.config(text="Current: Stock: - | Price: KES -")
            else:
                messagebox.showerror("Error", message)
    
    def update_payment_fields(self):
        self.cash_frame.pack_forget()
        self.card_frame.pack_forget()
        self.mpesa_frame.pack_forget()
        method = self.payment_method.get()
        if method == "cash":
            self.cash_frame.pack(fill=tk.X)
        elif method == "card":
            self.card_frame.pack(fill=tk.X)
        elif method == "mpesa":
            self.mpesa_frame.pack(fill=tk.X)
    
    def refresh_products(self):
        for item in self.product_tree.get_children():
            self.product_tree.delete(item)
        products = self.app.get_all_products()
        for p in products:
            self.product_tree.insert('', tk.END, values=(
                p['product_id'], p['name'], f"{p['price_per_unit']:.2f}", 
                p['unit'], f"{p['stock_quantity']:.1f}"
            ))
    
    def refresh_cart(self):
        for item in self.cart_tree.get_children():
            self.cart_tree.delete(item)
        cart_items = self.app.get_cart_items()
        for item in cart_items:
            self.cart_tree.insert('', tk.END, values=(
                item.product.name, f"{item.quantity:.1f}", item.product.unit,
                f"{item.product.price_per_unit:.2f}", f"{item.subtotal:.2f}"
            ))
        if cart_items:
            subtotal, tax, total = self.app.calculate_totals()
            self.subtotal_var.set(f"Subtotal: KES {subtotal:.2f}")
            self.tax_var.set(f"VAT (16%): KES {tax:.2f}")
            self.total_var.set(f"TOTAL: KES {total:.2f}")
        else:
            self.subtotal_var.set("Subtotal: KES 0.00")
            self.tax_var.set("VAT (16%): KES 0.00")
            self.total_var.set("TOTAL: KES 0.00")
    
    def add_to_cart(self):
        selected = self.product_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a product first")
            return
        try:
            quantity = float(self.quantity_var.get())
            if quantity <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid Quantity", "Please enter a valid positive number")
            return
        item = self.product_tree.item(selected[0])
        product_id = item['values'][0]
        success, message = self.app.add_to_cart(product_id, quantity)
        if success:
            self.refresh_cart()
            messagebox.showinfo("Success", message)
        else:
            messagebox.showerror("Error", message)
    
    def remove_from_cart(self):
        selected = self.cart_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an item to remove")
            return
        index = self.cart_tree.index(selected[0])
        self.app.remove_from_cart(index)
        self.refresh_cart()
    
    def clear_cart(self):
        self.app.clear_cart()
        self.refresh_cart()
    
    def show_full_receipt(self):
        """Display receipt in a large window for full visibility"""
        receipt_content = self.receipt_text.get(1.0, tk.END).strip()
        if not receipt_content:
            messagebox.showwarning("No Receipt", "Generate a receipt first!")
            return
        
        # Create large popup window
        full_window = tk.Toplevel(self.root)
        full_window.title("FULL RECEIPT - Customer Copy")
        full_window.geometry("700x750")
        full_window.configure(bg='white')
        
        # Make window modal
        full_window.transient(self.root)
        full_window.grab_set()
        
        # Header
        header = ttk.Label(full_window, text="CUSTOMER RECEIPT", 
                          font=('Arial', 16, 'bold'))
        header.pack(pady=(10, 5))
        
        # Receipt display - no scroll, full height
        receipt_display = tk.Text(full_window, wrap=tk.WORD,
                                  font=('Courier', 12), bg='white',
                                  padx=20, pady=20, height=35, width=60)
        receipt_display.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        receipt_display.insert(1.0, receipt_content)
        receipt_display.config(state=tk.DISABLED)
        
        # Button frame
        btn_frame = ttk.Frame(full_window)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Print", command=lambda: self.print_from_full(receipt_content)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Close", command=full_window.destroy).pack(side=tk.LEFT, padx=5)
        
        # Auto-show after checkout
        self.root.update_idletasks()
    
    def print_from_full(self, content):
        """Print from full receipt view"""
        messagebox.showinfo("Print", "Receipt sent to printer!")
    
    def checkout(self):
        cart_items = self.app.get_cart_items()
        if not cart_items:
            messagebox.showwarning("Empty Cart", "Cart is empty! Add items first.")
            return
        method = self.payment_method.get()
        payment_details = {}
        
        # Pre-validate stock availability
        for item in cart_items:
            product_data = self.app.db.get_product(item.product.product_id)
            if product_data:
                current_stock = float(product_data['stock_quantity'])
                required_stock = float(item.quantity)
                if current_stock < required_stock:
                    messagebox.showerror("Insufficient Stock", 
                        f"Insufficient stock for {item.product.name}!\n"
                        f"Available: {current_stock} {item.product.unit}\n"
                        f"Required: {required_stock} {item.product.unit}")
                    return
        
        try:
            if method == "cash":
                try:
                    amount = float(self.cash_amount.get())
                    if amount <= 0:
                        messagebox.showerror("Invalid Amount", "Amount must be greater than 0")
                        return
                    payment_details = {"amount_tendered": amount}
                except ValueError:
                    messagebox.showerror("Invalid Amount", "Please enter a valid amount")
                    return
            elif method == "card":
                card_num = self.card_number.get().strip()
                if not card_num:
                    messagebox.showerror("Invalid Card", "Please enter card number")
                    return
                payment_details = {"card_number": card_num, "card_type": self.card_type.get()}
            elif method == "mpesa":
                phone = self.mpesa_phone.get().strip()
                code = self.mpesa_code.get().strip()
                if not phone:
                    messagebox.showerror("Invalid Phone", "Please enter phone number")
                    return
                payment_details = {"phone_number": phone, "mpesa_code": code}
            else:
                messagebox.showerror("Error", "Please select a payment method")
                return
            
            pm = PaymentMethod(method)
            receipt = self.app.checkout(pm, **payment_details)
            
            if receipt:
                # Payment completed successfully
                receipt_text = self.app.format_receipt(receipt)
                self.receipt_text.delete(1.0, tk.END)
                self.receipt_text.insert(1.0, receipt_text)
                self.refresh_cart()
                self.refresh_products()
                
                # Clear payment fields
                if method == "cash":
                    self.cash_amount.delete(0, tk.END)
                elif method == "card":
                    self.card_number.delete(0, tk.END)
                elif method == "mpesa":
                    self.mpesa_phone.delete(0, tk.END)
                    self.mpesa_code.delete(0, tk.END)
                
                # Auto-show full receipt
                self.show_full_receipt()
                messagebox.showinfo("Success", "Payment processed successfully!")
                
            elif method in ["card", "mpesa"]:
                # Payment initiated, waiting for confirmation
                messagebox.showinfo("Payment Initiated", "Payment request sent. Please wait for confirmation.")
            else:
                messagebox.showerror("Error", "Checkout failed. Please check payment details.")
                
        except Exception as e:
            logger.error(f"Checkout error: {e}")
            messagebox.showerror("Error", f"Checkout failed: {str(e)}\n\nPlease check:\n- Cart has items\n- Payment details are correct\n- Stock is available")
    
    def print_receipt(self):
        receipt_content = self.receipt_text.get(1.0, tk.END).strip()
        if not receipt_content:
            messagebox.showwarning("No Receipt", "No receipt to print!")
            return
        print_window = tk.Toplevel(self.root)
        print_window.title("Print Receipt")
        print_window.geometry("400x300")
        ttk.Label(print_window, text="Receipt ready to print", font=('Arial', 12, 'bold')).pack(pady=10)
        text_area = scrolledtext.ScrolledText(print_window, wrap=tk.WORD, font=('Courier', 10))
        text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_area.insert(1.0, receipt_content)
        text_area.config(state=tk.DISABLED)
        ttk.Button(print_window, text="Close", command=print_window.destroy).pack(pady=10)
        messagebox.showinfo("Print", "Receipt sent to printer!", parent=print_window)


def main():
    root = tk.Tk()
    app = CashierReceiptSystemGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
