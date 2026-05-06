#!/usr/bin/env python3
"""CFO Discovery Request to OfficeAssistant"""
import sys
import os
import json

# Change to the crewai directory 
os.chdir('/home/zoltan/srv/crewai')

# Add paths for imports
sys.path.insert(0, '/home/zoltan/srv/crewai/src')
sys.path.insert(0, '/home/zoltan/srv/crewai/ai_council')

from agent_bus.agent_bus import AgentBus

bus = AgentBus()

# Comprehensive CFO discovery request
request = """
CFO DISCOVERY REQUEST — AESTAS HEALTHCARE LTD

OfficeAssistant, I need a complete company briefing for CFO advisory purposes. Please provide detailed information on ALL of the following:

## 1. LEGAL ENTITY STRUCTURE
- Exact legal entity names for Cyprus, Sweden, and Hungary operations
- Incorporation documents and registration numbers
- Ownership structure (shareholders, percentages)
- Registered addresses in each jurisdiction
- Any subsidiary or related entity relationships

## 2. FINANCIAL RECORDS
- Bank account details (institutions, account numbers, balances, signatories)
- Revenue figures (monthly/quarterly breakdown for last 12 months)
- Expense categories and totals
- Current burn rate (monthly cash burn)
- Tax identification numbers and filing status in each jurisdiction
- Most recent tax returns or notices

## 3. CONTRACTS
- All active client contracts (client name, value, term, renewal dates)
- Vendor/supplier agreements (vendor name, amount, terms)
- Employment contracts (employee names, roles, compensation, start dates)
- Contractor agreements (names, roles, rates, terms)
- Partnership or joint venture agreements
- NDAs or other material agreements

## 4. INSURANCE POLICIES
- Current policies (provider, coverage type, policy numbers, premiums, expiry dates)
- Coverage limits and deductibles
- Claims history

## 5. REGULATORY LICENSES
- Cyprus Medical Council registration (license number, status, expiry)
- Swedish healthcare permits (type, number, status, expiry)
- Hungarian medical credentials (type, number, status, expiry)
- Any pending regulatory applications or inspections

## 6. TEAM/CONTRACTORS
- Full team roster with roles and responsibilities
- Employment vs contractor classification
- Compensation details (salary, bonuses, equity if any)
- Employment agreements and their locations
- Any HR policies in place

## 7. INTELLECTUAL PROPERTY
- Trademarks (name, registration number, jurisdiction, status)
- Patents (number, jurisdiction, status, expiry)
- Domain names and ownership
- Brand assets (logos, proprietary materials)
- Any IP assignment agreements

## 8. OUTSTANDING LIABILITIES
- Loans (lender, principal, interest rate, repayment schedule, collateral)
- Accounts payable (amounts, due dates, vendors)
- Legal claims or pending litigation
- Commitments or contingencies
- Any guarantees or sureties

## 9. BUDGET VS ACTUALS & FORECASTS
- Annual budget documents
- Monthly actuals vs budget comparisons
- Cash flow forecasts
- Financial models or projections
- Key performance indicators tracked

## 10. INVESTOR/SHAREHOLDER DOCUMENTATION
- Shareholder agreements
- Investment agreements or term sheets
- Cap table with ownership percentages
- Any convertible notes or SAFE agreements
- Previous funding rounds details
- Due diligence materials from investors

Please provide SPECIFIC details: exact numbers, dates, entity names, document locations, dollar amounts, and percentages. Vague answers are not acceptable for CFO-level advisory work.

If you don't have certain information, please clearly state what's missing so I can escalate to Zoltan directly.
"""

print("Sending comprehensive CFO discovery request to OfficeAssistant...")
# Use call to send request to office_assistant and wait for response
response = bus.call("office_assistant", request, timeout=120)
print("\n=== RESPONSE FROM OFFICEASSISTANT ===")
print(response)
