#!/usr/bin/env python3
"""
Test script for multiline message handling.
Run this to verify message splitting works correctly.
"""

def test_message_splitting():
    """Test the message splitting logic"""
    
    # Simulate a long response
    test_response = """Sure, here's a list of cheeses:

1. Cheddar - A sharp, aged cheese perfect for sandwiches
2. Brie - A creamy, soft cheese with a white rind
3. Gouda - A Dutch cheese with a nutty flavor
4. Mozzarella - Fresh Italian cheese, great for pizza
5. Blue cheese - Strong flavored cheese with blue veins
6. Parmesan - Hard Italian cheese, perfect for grating
7. Swiss - Cheese with distinctive holes, mild flavor
8. Feta - Greek cheese, crumbly and salty
9. Camembert - French cheese similar to brie
10. Manchego - Spanish sheep's milk cheese

Each of these cheeses has unique characteristics and uses in cooking. Would you like more details about any specific cheese?"""

    print("🧪 Testing multiline message splitting")
    print("=" * 50)
    print(f"Original response length: {len(test_response)} chars")
    print()
    
    # Test the splitting logic
    cleaned_response = test_response.replace('\r\n', '\n').replace('\r', '\n')
    
    if len(cleaned_response) > 1900:
        print("Response too long - would split into multiple messages")
        
        # Split at natural break points
        parts = []
        current_part = ""
        
        for line in cleaned_response.split('\n'):
            if len(current_part) + len(line) + 1 > 1900:
                if current_part:
                    parts.append(current_part.strip())
                    current_part = line
                else:
                    # Single line is too long, split it
                    parts.append(line[:1900] + "...")
                    current_part = ""
            else:
                current_part += line + '\n'
        
        if current_part:
            parts.append(current_part.strip())
        
        print(f"Would send {len(parts)} message parts:")
        print()
        
        for i, part in enumerate(parts):
            print(f"--- Part {i+1}/{len(parts)} ({len(part)} chars) ---")
            print(part)
            print()
    else:
        print("Response short enough for single message")
        print(f"Content: {cleaned_response}")

if __name__ == "__main__":
    test_message_splitting() 