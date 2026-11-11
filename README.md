# VendorGate: vendor onboarding, from submission to decision

**Principle:** AI reads, rules decide, humans own the grey zone.

## Run it
    pip install -r requirements.txt
    python build_data.py      # generates mock vendor master, GST registry, scenarios
    python run_cli.py         # runs every scenario in the terminal
    streamlit run app.py      # opens the app in your browser

## Statuses
- **Approved**: every check passed
- **Pending (Vendor action)**: something the vendor can fix; they get an exact list
- **Pending (Internal review)**: data contradicts itself; a person decides
- **Rejected**: fraud signal or ineligible; the vendor is not told which check failed

## Assumptions
1. Indian vendors are GST-registered (non-registered vendors need a declaration; out of scope).
2. The GST registry and penny-drop verification are mocked; IFSC lookup is live (Razorpay API) with an offline fallback.
3. Rejected only for fraud or ineligibility. A legitimate vendor rejected for a typo costs the business; anything fixable stays Pending.
4. The vendor master is the company's existing approved vendor list.
5. Name-match thresholds: >=88 match, 70-87 human review, <70 flagged.
6. All PANs, GSTINs and account numbers are fictional (GSTINs use the real check-digit algorithm).
