# Fresh Fruits Market - Cashier Receipt System

A unified Python-based receipt system for fruit vendors with MongoDB database and multiple payment integrations.

## Files

| File                        | Description                                                     |
| --------------------------- | --------------------------------------------------------------- |
| `marketreceipt.py`          | **Main Application** - Unified GUI for cashier to process sales |
| `FreshFruitsMarket.desktop` | Desktop icon - double-click to open GUI                         |
| `requirements.txt`          | Python dependencies                                             |

## Requirements

**MongoDB is REQUIRED** - The system will not work without it.

## Setup

### 1. Install MongoDB

```bash
sudo apt update
sudo apt install mongodb
sudo systemctl start mongodb
sudo systemctl enable mongodb
```

Verify MongoDB is running:

```bash
sudo systemctl status mongodb
```

### 2. Install Python dependencies

```bash
pip install pymongo
```

### 3. Install Desktop Icon (Optional)

```bash
# Make the desktop file executable
chmod +x FreshFruitsMarket.desktop

# Copy to Desktop
cp FreshFruitsMarket.desktop ~/Desktop/
chmod +x ~/Desktop/FreshFruitsMarket.desktop
```

Now you can double-click the desktop icon to launch the GUI!

## Usage

### Main Application (GUI - For Cashiers)

**Method 1: Desktop Icon**

- Double-click "Fresh Fruits Market" icon on your desktop

**Method 2: Command Line**

```bash
python marketreceipt.py
```

The cashier GUI provides:

- **Product List**: View all available products with prices and stock
- **Add to Cart**: Select product, enter quantity, click "ADD TO CART"
- **Cart Display**: Shows products with price per item and subtotals
- **Total Calculation**: Automatic subtotal, VAT (16%), and TOTAL display
- **Payment Methods**: Cash, Card (Visa/Mastercard/ATM), or M-Pesa
- **Stock Deduction**: Automatically deducts sold quantities from database
- **Receipt Generation**: Creates receipt to give to customer

## Example Receipt Output

```
============================================================
           FRESH FRUITS MARKET
        123 Market Street, Nairobi
          Tel: +254 700 123 456
============================================================
Receipt No: RCP-A3B7C9D2
Date: 2026-03-01          Time: 14:30:25
------------------------------------------------------------
Item              Qty       Price       Total
------------------------------------------------------------
Apples            2.0 kg    150.00      300.00
Bananas           3.0 bunch 80.00       240.00
------------------------------------------------------------
Subtotal:                              540.00
VAT (16%):                             86.40
TOTAL:                                 626.40
------------------------------------------------------------
Payment: CASH
Amount Paid: 1000.00
BALANCE: 373.60
============================================================
     Thank you for shopping with us!
        Please come again!
============================================================
```

## Payment Methods

### 1. Cash

- Enter amount tendered by customer
- System calculates and displays balance

### 2. Card (ATM/Mastercard/Visa)

- Select card type
- Enter card number (last 4 digits masked on receipt)
- System processes payment

### 3. M-Pesa

- Enter M-Pesa phone number
- Enter M-Pesa transaction code
- Reference number displayed on receipt

## How It Works

1. **Cashier selects products** from the available list
2. **Enters quantity** for each product
3. **System displays** price per product and running total
4. **Customer chooses payment method**
5. **System processes payment** and generates receipt
6. **Stock is automatically deducted** from MongoDB database
7. **Receipt is displayed** for the customer

## Integration Notes

- **Card Payments**: Currently simulated. For production, integrate with:

  - DPO Pay (Africa)
  - Stripe
  - Pesapal

- **M-Pesa Integration**: Currently simulated. For production, use:
  - Safaricom Daraja API: https://developer.safaricom.co.ke/
  - Implement STK push for real payments

## Database Schema

**Products Collection**:

- `product_id`: Unique identifier
- `name`: Product name
- `price_per_unit`: Price per unit
- `unit`: Unit of measurement (kg, piece, bunch, etc.)
- `stock_quantity`: Available stock

**Receipts Collection**:

- `receipt_number`: Unique receipt ID
- `date`, `time`: Transaction timestamp
- `items`: Array of purchased items
- `subtotal`, `tax_amount`, `total_amount`: Financial summary
- `payment`: Payment method and details
- `created_at`: Database timestamp
