#!/usr/bin/env python3
"""
Type Safety utilities for Fresh Fruits Market
Ensures consistent type handling throughout the application
"""

from decimal import Decimal, InvalidOperation
from typing import Union, Optional, Any
import logging

logger = logging.getLogger(__name__)


class TypeConverter:
    """Utility class for safe type conversions"""
    
    @staticmethod
    def to_decimal(value: Any, field_name: str = "value") -> Decimal:
        """Safely convert any value to Decimal"""
        if isinstance(value, Decimal):
            return value
        
        if value is None:
            raise ValueError(f"{field_name} cannot be None")
        
        try:
            # Handle string inputs
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    raise ValueError(f"{field_name} cannot be empty")
                return Decimal(value)
            
            # Handle numeric inputs
            if isinstance(value, (int, float)):
                return Decimal(str(value))
            
            raise TypeError(f"Cannot convert {type(value)} to Decimal for {field_name}")
            
        except (InvalidOperation, ValueError) as e:
            raise ValueError(f"Invalid {field_name}: {value}") from e
    
    @staticmethod
    def to_positive_decimal(value: Any, field_name: str = "value") -> Decimal:
        """Convert to positive Decimal (greater than 0)"""
        decimal_value = TypeConverter.to_decimal(value, field_name)
        if decimal_value <= 0:
            raise ValueError(f"{field_name} must be greater than 0, got {decimal_value}")
        return decimal_value
    
    @staticmethod
    def to_non_negative_decimal(value: Any, field_name: str = "value") -> Decimal:
        """Convert to non-negative Decimal (0 or greater)"""
        decimal_value = TypeConverter.to_decimal(value, field_name)
        if decimal_value < 0:
            raise ValueError(f"{field_name} cannot be negative, got {decimal_value}")
        return decimal_value
    
    @staticmethod
    def to_string(value: Any, field_name: str = "value", allow_empty: bool = True) -> str:
        """Safely convert to string with validation"""
        if value is None:
            if allow_empty:
                return ""
            raise ValueError(f"{field_name} cannot be None")
        
        str_value = str(value).strip()
        
        if not allow_empty and not str_value:
            raise ValueError(f"{field_name} cannot be empty")
        
        return str_value


class ValidatedProduct:
    """Product with enforced type safety"""
    
    def __init__(self, name: str, price_per_unit: Any, unit: str, stock_quantity: Any, product_id: Optional[str] = None):
        self.name = TypeConverter.to_string(name, "name", allow_empty=False)
        self.price_per_unit = TypeConverter.to_positive_decimal(price_per_unit, "price_per_unit")
        self.unit = TypeConverter.to_string(unit, "unit", allow_empty=False)
        self.stock_quantity = TypeConverter.to_non_negative_decimal(stock_quantity, "stock_quantity")
        self.product_id = product_id or self._generate_product_id()
    
    def _generate_product_id(self) -> str:
        """Generate a unique product ID"""
        import uuid
        return str(uuid.uuid4())[:8].upper()
    
    def to_dict(self) -> dict:
        """Convert to dictionary with string values for MongoDB"""
        return {
            "name": self.name,
            "price_per_unit": str(self.price_per_unit),
            "unit": self.unit,
            "stock_quantity": str(self.stock_quantity),
            "product_id": self.product_id
        }


class ValidatedCartItem:
    """Cart item with enforced type safety"""
    
    def __init__(self, product: ValidatedProduct, quantity: Any):
        self.product = product
        self.quantity = TypeConverter.to_positive_decimal(quantity, "quantity")
    
    @property
    def subtotal(self) -> Decimal:
        """Calculate subtotal with type safety"""
        return self.product.price_per_unit * self.quantity
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            "product": self.product.to_dict(),
            "quantity": str(self.quantity),
            "subtotal": str(self.subtotal)
        }


class ValidatedPaymentDetails:
    """Payment details with enforced type safety"""
    
    def __init__(self, method: str, amount_paid: Any, **kwargs):
        from enum import Enum
        
        # Validate payment method
        valid_methods = ["cash", "card", "mpesa"]
        if method.lower() not in valid_methods:
            raise ValueError(f"Invalid payment method: {method}")
        
        self.method = method.lower()
        self.amount_paid = TypeConverter.to_positive_decimal(amount_paid, "amount_paid")
        self.balance = TypeConverter.to_decimal(kwargs.get("balance", "0"), "balance")
        
        # Optional fields
        self.transaction_reference = TypeConverter.to_string(
            kwargs.get("transaction_reference", ""), "transaction_reference"
        )
        self.phone_number = TypeConverter.to_string(
            kwargs.get("phone_number", ""), "phone_number"
        )
        self.card_last_four = TypeConverter.to_string(
            kwargs.get("card_last_four", ""), "card_last_four"
        )
        self.card_type = TypeConverter.to_string(
            kwargs.get("card_type", ""), "card_type"
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            "method": self.method,
            "amount_paid": str(self.amount_paid),
            "balance": str(self.balance),
            "transaction_reference": self.transaction_reference,
            "phone_number": self.phone_number,
            "card_last_four": self.card_last_four,
            "card_type": self.card_type
        }


class InputValidator:
    """Comprehensive input validation for GUI inputs"""
    
    @staticmethod
    def validate_product_name(name: str) -> str:
        """Validate product name"""
        name = TypeConverter.to_string(name, "name", allow_empty=False)
        if len(name) < 2:
            raise ValueError("Product name must be at least 2 characters")
        if len(name) > 100:
            raise ValueError("Product name must be less than 100 characters")
        return name
    
    @staticmethod
    def validate_unit(unit: str) -> str:
        """Validate product unit"""
        valid_units = ["kg", "piece", "bunch", "punnet", "box", "liter", "dozen"]
        unit = TypeConverter.to_string(unit, "unit", allow_empty=False).lower()
        if unit not in valid_units:
            raise ValueError(f"Invalid unit. Valid units: {', '.join(valid_units)}")
        return unit
    
    @staticmethod
    def validate_card_number(card_number: str) -> str:
        """Validate card number"""
        import re
        
        card_number = TypeConverter.to_string(card_number, "card_number", allow_empty=False)
        # Remove spaces and dashes
        clean_number = re.sub(r'[\s-]', '', card_number)
        
        if not re.match(r'^\d{13,19}$', clean_number):
            raise ValueError("Card number must be 13-19 digits")
        
        return clean_number
    
    @staticmethod
    def validate_phone_number(phone_number: str) -> str:
        """Validate phone number"""
        import re
        
        phone_number = TypeConverter.to_string(phone_number, "phone_number", allow_empty=False)
        
        if not re.match(r'^\+?\d{10,15}$', phone_number):
            raise ValueError("Phone number must be 10-15 digits, optionally starting with +")
        
        return phone_number
    
    @staticmethod
    def validate_quantity(quantity: Any) -> Decimal:
        """Validate quantity input"""
        return TypeConverter.to_positive_decimal(quantity, "quantity")
    
    @staticmethod
    def validate_price(price: Any) -> Decimal:
        """Validate price input"""
        price = TypeConverter.to_positive_decimal(price, "price")
        if price > Decimal('999999.99'):
            raise ValueError("Price cannot exceed 999,999.99")
        return price
    
    @staticmethod
    def validate_stock(stock: Any) -> Decimal:
        """Validate stock input"""
        return TypeConverter.to_non_negative_decimal(stock, "stock")


# Decorator for automatic type conversion
def validate_types(**type_validators):
    """Decorator to validate function parameters"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Convert and validate parameters
            validated_kwargs = {}
            for param_name, validator in type_validators.items():
                if param_name in kwargs:
                    validated_kwargs[param_name] = validator(kwargs[param_name])
            
            # Update kwargs with validated values
            kwargs.update(validated_kwargs)
            return func(*args, **kwargs)
        return wrapper
    return decorator


# Example usage:
# @validate_types(
#     price=InputValidator.validate_price,
#     stock=InputValidator.validate_stock,
#     name=InputValidator.validate_product_name
# )
# def add_product(name, price, unit, stock):
#     # Function implementation with validated inputs
#     pass
