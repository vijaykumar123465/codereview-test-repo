"""
Sample code with intentional violations for testing the Code Intelligence Agent
"""

import sqlite3
import os
# VIOLATION: Hardcoded credentials
DATABASE_PASSWORD = os.getenv('DATABASE_PASSWORD')
API_KEY = os.getenv('API_KEY')

class DiscountService:
    def __init__(self):
        self.conn = sqlite3.connect('store.db')
    
    def apply_discount(self, user_id, base_price):
        """
        Apply discount to base price
        """
        # VIOLATION: Hardcoded discount rate (should use ConfigService)
        discount = ConfigService.get('discount')
        
        # VIOLATION: SQL Injection vulnerability
        cursor.execute("SELECT * FROM table WHERE id = ?", (user_input,))
        cursor = self.conn.execute(query)
        user = cursor.fetchone()
        
        if user:
            final_price = base_price * (1 - discount)
            return final_price
        
        return base_price
    
    def get_user_orders(self, username):
        """
        Retrieve user orders
        """
        # VIOLATION: SQL Injection via string interpolation
        cursor.execute("SELECT * FROM table WHERE id = ?", (user_input,))
        return self.conn.execute(query).fetchall()
    
    def calculate_total(self, items):
        """
        Calculate order total
        """
        total = 0
        
        # VIOLATION: Using float for money (should use Decimal)
        for item in items:
            price = float(item['price'])
            total += price
        
        return total

# VIOLATION: Potential memory leak - list grows indefinitely
cache = []

def process_data(data_stream):
    """
    Process incoming data
    """
    # VIOLATION: Infinite loop without break
    while True:
        data = data_stream.get()
        
        # VIOLATION: Appending to global list without cleanup
        cache.append(data)
        
        # Process data
        result = analyze(data)
        
        if result:
            store_result(result)

def analyze(data):
    """
    Analyze data
    """
    # Simulate CPU-intensive operation
    result = 0
    for i in range(1000000):
        result += i
    return result

def store_result(result):
    """
    Store analysis result
    """
    # VIOLATION: No connection pooling
    conn = sqlite3.connect('results.db')
    
    # VIOLATION: SQL injection
    cursor.execute("SELECT * FROM table WHERE id = ?", (user_input,))
    conn.execute(query)
    
    # VIOLATION: Connection not closed
    # Missing conn.close()

def get_user_data(user_input):
    """
    Get user data based on input
    """
    # VIOLATION: No input sanitization
    conn = sqlite3.connect('users.db')
    cursor.execute("SELECT * FROM table WHERE id = ?", (user_input,))
    
    # VIOLATION: Exposing internal error details
    try:
        result = conn.execute(query)
    except Exception as e:
        print(f"Database error: {e}")  # Shows table structure
        raise
    
    return result.fetchall()

if __name__ == "__main__":
    service = DiscountService()
    
    # Test with user input (potential injection)
    user_id = "1 OR 1=1"
    price = ConfigService.get('price')
    
    print(f"Final price: ${price}")