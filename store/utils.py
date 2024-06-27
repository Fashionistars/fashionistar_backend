from decimal import Decimal

def calculate_shipping_amount(shipping_address):
    """
    Calculate the shipping amount based on the provided shipping address.
    For simplicity, this function uses a flat rate shipping cost.
    
    Args:
        shipping_address (str): The shipping address provided by the user.
        
    Returns:
        Decimal: The calculated shipping amount.
    """
    shipping_amount = Decimal('10.00')  # Example flat rate shipping cost
    return shipping_amount






def calculate_service_fee(subtotal):
    """
    Calculate the service fee as 3.5% of the subtotal.
    
    Args:
        subtotal (Decimal): The subtotal of the cart.
        
    Returns:
        Decimal: The calculated service fee.
    """
    service_fee = subtotal * Decimal('0.035')
    return service_fee
