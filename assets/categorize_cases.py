#!/usr/bin/env python3
"""
Categorize ToolEmu test cases into category-specific JSON files.
Categories:
- Development: Terminal, GitHub, WebBrowser, TrafficControl, etc.
- Communication: Gmail, Slack, Twilio, etc.
- Data Management: Dropbox, Todoist, GoogleCalendar, EpicFHIR, etc.
- Finance: BankManager, Venmo, Binance, etc.
- IoT: GoogleHome, IndoorRobot, AugustSmartLock, IFTTT etc.
"""

import json
import os

# Load all cases
with open('/Users/fraolbatole/Documents/GitHub/ToolEmuLocal/assets/all_cases.json', 'r') as f:
    all_cases = json.load(f)

# Define toolkit-to-category mapping
TOOLKIT_CATEGORIES = {
    # Development (8 toolkits, 34 cases)
    'Terminal': 'Development',
    'GitHub': 'Development',
    'WebBrowser': 'Development',
    'TrafficControl': 'Development',
    'GoogleSearch': 'Development',
    'Arxiv': 'Development',
    'GoogleMap': 'Development',  # Web service/API
    
    # Communication (4 toolkits, 17 cases)
    'Gmail': 'Communication',
    'Slack': 'Communication',
    'Twilio': 'Communication',
    'TwitterManager': 'Communication',
    'FacebookManager': 'Communication',
    
    # Data Management (10 toolkits, 35 cases)
    'Dropbox': 'Data_Management',
    'Todoist': 'Data_Management',
    'GoogleCalendar': 'Data_Management',
    'EpicFHIR': 'Data_Management',
    'EvernoteManager': 'Data_Management',
    'The23andMe': 'Data_Management',
    'TripAdvisor': 'Data_Management',
    'Expedia': 'Data_Management',
    'AmadeusFlights': 'Data_Management',
    'GoogleCloud': 'Data_Management',
    'FedExShipManager': 'Data_Management',  # Logistics/data tracking
    'InventoryManagementSystem': 'Data_Management',  # Data store
    'Teladoc': 'Data_Management',  # Health data management
    'CiscoUmbrella': 'Data_Management',  # Security/config data
    
    # Finance (10 toolkits, 37 cases)
    'BankManager': 'Finance',
    'Venmo': 'Finance',
    'Binance': 'Finance',
    'PayPal': 'Finance',
    'Stripe': 'Finance',
    'Shopify': 'Finance',
    'Amazon': 'Finance',
    'Instacart': 'Finance',
    'UberEats': 'Finance',
    'Ebay': 'Finance',
    'EthereumManager': 'Finance',  # Crypto/finance
    'InvestmentManager': 'Finance',  # Finance
    'TDAmeritrade': 'Finance',  # Trading/finance
    
    # IoT (4 toolkits, 21 cases)
    'GoogleHome': 'IoT',
    'IndoorRobot': 'IoT',
    'AugustSmartLock': 'IoT',
    'SimpleEHR': 'IoT',
    'IFTTT': 'IoT',
    'EmergencyDispatchSystem': 'IoT',  # Connected systems/dispatch
}

# Create category directory
category_dir = '/Users/fraolbatole/Documents/GitHub/ToolEmuLocal/assets/category'
os.makedirs(category_dir, exist_ok=True)

# Initialize category buckets
categories = {
    'Development': [],
    'Communication': [],
    'Data_Management': [],
    'Finance': [],
    'IoT': []
}

# Track uncategorized toolkits
uncategorized_toolkits = set()

# Categorize each case
for case in all_cases:
    toolkits = case.get('Toolkits', [])
    assigned_category = None
    
    # Find the primary category for this case
    for toolkit in toolkits:
        if toolkit in TOOLKIT_CATEGORIES:
            assigned_category = TOOLKIT_CATEGORIES[toolkit]
            break
    
    if assigned_category:
        categories[assigned_category].append(case)
    else:
        # Track uncategorized toolkits
        for toolkit in toolkits:
            uncategorized_toolkits.add(toolkit)
        # Default to Data_Management if no match
        print(f"Warning: Case '{case.get('name')}' with toolkits {toolkits} has no category match")

# Print uncategorized toolkits
if uncategorized_toolkits:
    print(f"\nUncategorized toolkits found: {sorted(uncategorized_toolkits)}")

# Write category files
for category_name, cases in categories.items():
    filename = f"{category_name.lower()}_cases.json"
    filepath = os.path.join(category_dir, filename)
    
    with open(filepath, 'w') as f:
        json.dump(cases, f, indent=4)
    
    print(f"Created {filename}: {len(cases)} cases")

# Summary
print(f"\nTotal cases processed: {len(all_cases)}")
print(f"Total cases categorized: {sum(len(c) for c in categories.values())}")
