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
                    try:
                        row['token_pair_id'] = int(row.get('token_pair_id', 0))
                    except:
                        row['token_pair_id'] = 0

                    row['from_token_decimals'] = int(row.get('from_token_decimals', 18))

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
                    try:
                        row['network_fee_raw'] = int(row.get('network_fee', 0))
                    except:
                        row['network_fee_raw'] = 0

                    test_cases.append(row)
        except Exception as e:
            print(f"❌ Error reading test case file {self.filename}: {e}")
        return test_cases
