<<<<<<< HEAD
import os

# Bad: hardcoded password
DATABASE_PASSWORD = "super_secret_123"

# Bad: hardcoded discount
DISCOUNT_RATE = 0.20

# Bad: potential division by zero
def calculate_average(total, count):
    return total / count

# Good: using environment variable
API_KEY = os.getenv("API_KEY")
=======
import os

# Bad: hardcoded password
DATABASE_PASSWORD = "super_secret_123"

# Bad: hardcoded discount
DISCOUNT_RATE = 0.20

# Bad: potential division by zero
def calculate_average(total, count):
    return total / count

# Good: using environment variable
API_KEY = os.getenv("API_KEY")
>>>>>>> cf81f949b402dd3edc0d7342fabcbff448c554f9
