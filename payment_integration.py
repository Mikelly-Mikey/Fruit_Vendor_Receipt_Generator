#!/usr/bin/env python3
"""
Payment Integration Module for Fresh Fruits Market
Handles real-time payment processing with M-Pesa and Card integrations
"""

import threading
import time
import requests
import logging
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import tkinter as tk
from tkinter import messagebox

logger = logging.getLogger(__name__)


class PaymentStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PaymentNotification:
    transaction_id: str
    phone_number: str
    amount: float
    status: PaymentStatus
    timestamp: str
    reference: str


class MPesaIntegration:
    """M-Pesa API integration for real-time payment notifications"""
    
    def __init__(self, callback_url: str = None):
        self.callback_url = callback_url
        self.pending_transactions: Dict[str, Dict] = {}
        self.notification_callbacks: list = []
        
    def initiate_payment(self, phone_number: str, amount: float, reference: str) -> Dict:
        """Initiate M-Pesa payment request"""
        try:
            # Simulate M-Pesa API call
            transaction_id = f"MP{int(time.time())}"
            
            # Store pending transaction
            self.pending_transactions[transaction_id] = {
                "phone": phone_number,
                "amount": amount,
                "reference": reference,
                "status": PaymentStatus.PENDING,
                "timestamp": time.time()
            }
            
            # Simulate payment processing (in real implementation, this would call M-Pesa API)
            threading.Thread(
                target=self._simulate_payment_completion,
                args=(transaction_id,),
                daemon=True
            ).start()
            
            return {
                "success": True,
                "transaction_id": transaction_id,
                "message": f"Payment request sent to {phone_number}. Please check your phone."
            }
            
        except Exception as e:
            logger.error(f"M-Pesa payment initiation failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _simulate_payment_completion(self, transaction_id: str):
        """Simulate payment completion for testing"""
        time.sleep(5)  # Simulate processing time
        
        if transaction_id in self.pending_transactions:
            transaction = self.pending_transactions[transaction_id]
            transaction["status"] = PaymentStatus.COMPLETED
            
            # Notify GUI
            notification = PaymentNotification(
                transaction_id=transaction_id,
                phone_number=transaction["phone"],
                amount=transaction["amount"],
                status=PaymentStatus.COMPLETED,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                reference=transaction["reference"]
            )
            
            for callback in self.notification_callbacks:
                try:
                    callback(notification)
                except Exception as e:
                    logger.error(f"Callback notification failed: {e}")
    
    def add_notification_callback(self, callback: Callable):
        """Add callback for payment notifications"""
        self.notification_callbacks.append(callback)


class CardPaymentIntegration:
    """Card payment integration with real-time processing"""
    
    def __init__(self):
        self.pending_transactions: Dict[str, Dict] = {}
        self.notification_callbacks: list = []
    
    def process_card_payment(self, card_number: str, amount: float, card_type: str) -> Dict:
        """Process card payment"""
        try:
            transaction_id = f"CD{int(time.time())}"
            
            # Store pending transaction
            self.pending_transactions[transaction_id] = {
                "card_number": card_number[-4:],  # Store only last 4 digits
                "amount": amount,
                "card_type": card_type,
                "status": PaymentStatus.PROCESSING,
                "timestamp": time.time()
            }
            
            # Simulate card processing
            threading.Thread(
                target=self._simulate_card_processing,
                args=(transaction_id,),
                daemon=True
            ).start()
            
            return {
                "success": True,
                "transaction_id": transaction_id,
                "message": "Processing card payment..."
            }
            
        except Exception as e:
            logger.error(f"Card payment processing failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _simulate_card_processing(self, transaction_id: str):
        """Simulate card payment processing"""
        time.sleep(3)  # Simulate processing time
        
        if transaction_id in self.pending_transactions:
            transaction = self.pending_transactions[transaction_id]
            transaction["status"] = PaymentStatus.COMPLETED
            
            # Notify GUI
            notification = PaymentNotification(
                transaction_id=transaction_id,
                phone_number="",
                amount=transaction["amount"],
                status=PaymentStatus.COMPLETED,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                reference=f"{transaction['card_type']} ****{transaction['card_number']}"
            )
            
            for callback in self.notification_callbacks:
                try:
                    callback(notification)
                except Exception as e:
                    logger.error(f"Callback notification failed: {e}")
    
    def add_notification_callback(self, callback: Callable):
        """Add callback for payment notifications"""
        self.notification_callbacks.append(callback)


class PaymentNotificationWindow:
    """Window for displaying payment notifications"""
    
    def __init__(self, parent):
        self.parent = parent
        self.window = None
    
    def show_notification(self, notification: PaymentNotification):
        """Show payment notification popup"""
        if self.window and self.window.winfo_exists():
            self.window.destroy()
        
        self.window = tk.Toplevel(self.parent)
        self.window.title("Payment Notification")
        self.window.geometry("400x250")
        self.window.attributes('-topmost', True)
        
        # Style based on payment status
        if notification.status == PaymentStatus.COMPLETED:
            bg_color = "#d4edda"
            text_color = "#155724"
            title = "✅ Payment Completed!"
        else:
            bg_color = "#f8d7da"
            text_color = "#721c24"
            title = "❌ Payment Failed!"
        
        self.window.configure(bg=bg_color)
        
        # Title
        title_label = tk.Label(
            self.window, 
            text=title,
            font=('Arial', 16, 'bold'),
            bg=bg_color,
            fg=text_color
        )
        title_label.pack(pady=20)
        
        # Payment details
        details_frame = tk.Frame(self.window, bg=bg_color)
        details_frame.pack(pady=10)
        
        if notification.phone_number:
            tk.Label(
                details_frame,
                text=f"Phone: {notification.phone_number}",
                font=('Arial', 12),
                bg=bg_color,
                fg=text_color
            ).pack(anchor='w', pady=2)
        
        tk.Label(
            details_frame,
            text=f"Amount: KES {notification.amount:.2f}",
            font=('Arial', 12),
            bg=bg_color,
            fg=text_color
        ).pack(anchor='w', pady=2)
        
        tk.Label(
            details_frame,
            text=f"Transaction ID: {notification.transaction_id}",
            font=('Arial', 10),
            bg=bg_color,
            fg=text_color
        ).pack(anchor='w', pady=2)
        
        tk.Label(
            details_frame,
            text=f"Time: {notification.timestamp}",
            font=('Arial', 10),
            bg=bg_color,
            fg=text_color
        ).pack(anchor='w', pady=2)
        
        # Auto-close button
        close_button = tk.Button(
            self.window,
            text="OK",
            command=self.window.destroy,
            font=('Arial', 12),
            bg="#007bff",
            fg="white"
        )
        close_button.pack(pady=20)
        
        # Auto-close after 10 seconds
        self.window.after(10000, self._auto_close)
    
    def _auto_close(self):
        """Auto-close notification window"""
        if self.window and self.window.winfo_exists():
            self.window.destroy()


class InventoryManager:
    """Enhanced inventory management with reporting"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        
    def get_stock_movements(self, product_id: str = None, date_range: tuple = None) -> list:
        """Get stock movement history"""
        try:
            query = {}
            if product_id:
                query["product_id"] = product_id
            if date_range:
                query["timestamp"] = {"$gte": date_range[0], "$lte": date_range[1]}
            
            # Get transactions from receipts collection
            receipts = list(self.db.receipts.find(query).sort("created_at", -1))
            
            movements = []
            for receipt in receipts:
                for item in receipt.get("items", []):
                    movements.append({
                        "date": receipt.get("created_at"),
                        "product_name": item.get("product_name"),
                        "quantity": item.get("quantity"),
                        "unit_price": item.get("unit_price"),
                        "subtotal": item.get("subtotal"),
                        "transaction_type": "sale",
                        "receipt_number": receipt.get("receipt_number")
                    })
            
            return movements
        except Exception as e:
            logger.error(f"Failed to get stock movements: {e}")
            return []
    
    def get_inventory_report(self) -> Dict:
        """Generate comprehensive inventory report"""
        try:
            products = self.db.get_all_products()
            
            total_products = len(products)
            total_stock_value = 0
            low_stock_items = []
            
            for product in products:
                stock_value = float(product['price_per_unit']) * float(product['stock_quantity'])
                total_stock_value += stock_value
                
                if float(product['stock_quantity']) < 10:  # Low stock threshold
                    low_stock_items.append({
                        "name": product['name'],
                        "current_stock": float(product['stock_quantity']),
                        "unit": product['unit']
                    })
            
            return {
                "total_products": total_products,
                "total_stock_value": total_stock_value,
                "low_stock_items": low_stock_items,
                "products": products
            }
        except Exception as e:
            logger.error(f"Failed to generate inventory report: {e}")
            return {}
    
    def get_sales_summary(self, date_range: tuple = None) -> Dict:
        """Generate sales summary report"""
        try:
            query = {}
            if date_range:
                query["created_at"] = {"$gte": date_range[0], "$lte": date_range[1]}
            
            receipts = list(self.db.receipts.find(query))
            
            total_sales = 0
            total_transactions = len(receipts)
            payment_methods = {"cash": 0, "card": 0, "mpesa": 0}
            
            for receipt in receipts:
                total_sales += float(receipt.get("total_amount", 0))
                method = receipt.get("payment", {}).get("method", "cash")
                payment_methods[method] = payment_methods.get(method, 0) + 1
            
            return {
                "total_sales": total_sales,
                "total_transactions": total_transactions,
                "average_transaction": total_sales / total_transactions if total_transactions > 0 else 0,
                "payment_methods": payment_methods,
                "receipts": receipts
            }
        except Exception as e:
            logger.error(f"Failed to generate sales summary: {e}")
            return {}


class BusinessLogbook:
    """Business operations logbook for tracking all activities"""
    
    def __init__(self, db_manager):
        self.db = db_manager
        self.activities = db_manager.db["activities"]
    
    def log_activity(self, activity_type: str, description: str, user: str = "Cashier", details: Dict = None):
        """Log business activity"""
        try:
            activity = {
                "activity_type": activity_type,
                "description": description,
                "user": user,
                "details": details or {},
                "timestamp": time.time(),
                "date": time.strftime("%Y-%m-%d"),
                "time": time.strftime("%H:%M:%S")
            }
            
            self.activities.insert_one(activity)
            logger.info(f"Activity logged: {activity_type} - {description}")
            
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")
    
    def get_activities(self, activity_type: str = None, date_range: tuple = None) -> list:
        """Get logged activities"""
        try:
            query = {}
            if activity_type:
                query["activity_type"] = activity_type
            if date_range:
                query["timestamp"] = {"$gte": date_range[0], "$lte": date_range[1]}
            
            return list(self.activities.find(query).sort("timestamp", -1))
        except Exception as e:
            logger.error(f"Failed to get activities: {e}")
            return []
