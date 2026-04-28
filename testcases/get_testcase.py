import csv
import os

class GetTestCase:
    def __init__(self, filename):
        self.filename = os.path.join("testcases", filename)

    def get_test_cases(self):
        """
        Reads the new CSV format and returns a list of test cases.
        """
        test_cases = []
        try:
            with open(self.filename, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Parse relevant fields
                    row['token_pair_id'] = int(row['token_pair_id'])
                    row['from_token_decimals'] = int(row['from_token_decimals'])

                    # Parse destination chain ID
                    to_chain_id_str = row.get('to_chain_slip44_id', '2153201998')
                    try:
                        if to_chain_id_str.startswith('0x'):
                            row['to_chain_id'] = int(to_chain_id_str, 16)
                        else:
                            row['to_chain_id'] = int(to_chain_id_str)
                    except:
                        row['to_chain_id'] = 2153201998

                    # Convert cross_amount(eth) to raw units (lamports or token smallest units)
                    cross_amount_eth = float(row['cross_amount(eth)'])
                    row['amount_raw'] = int(cross_amount_eth * (10 ** row['from_token_decimals']))

                    # Network fee in raw units (usually lamports)
                    row['network_fee_raw'] = int(row['network_fee'])

                    test_cases.append(row)
        except Exception as e:
            print(f"❌ Error reading test case file {self.filename}: {e}")
        return test_cases
