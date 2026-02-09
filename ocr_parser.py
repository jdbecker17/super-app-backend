import re
import sys
import pdfplumber

class BrokerageNoteParser:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.transactions = []
        self.metadata = {
            "broker": None,
            "date": None,
            "net_value": 0.0,
            "fees": 0.0
        }

    def parse(self):
        try:
            import pdfplumber
        except ImportError:
            print("❌ Erro: Biblioteca 'pdfplumber' não instalada.")
            print("Execute: pip install pdfplumber")
            return None

        with pdfplumber.open(self.pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                full_text += text
                self._extract_page_data(text)
        
        return {
            "metadata": self.metadata,
            "transactions": self.transactions
        }

    def _extract_page_data(self, text):
        # 1. Extract Date (Data pregão)
        # Pattern: "Data pregão" followed by date
        if not self.metadata["date"]:
            date_match = re.search(r'Data pregão\s+(\d{2}/\d{2}/\d{4})', text, re.IGNORECASE)
            if date_match:
                self.metadata["date"] = date_match.group(1)

        # 2. Extract Broker (Simplistic)
        if not self.metadata["broker"]:
            if "XP INVESTIMENTOS" in text: self.metadata["broker"] = "XP"
            elif "CLEAR" in text: self.metadata["broker"] = "Clear"
            elif "RICO" in text: self.metadata["broker"] = "Rico"
            elif "NU INVEST" in text: self.metadata["broker"] = "NuInvest"

        # 3. Extract Transactions (SINACUR standard lines)
        # Q Negociação C/V Tipo mercado Prazo Especificação do título Obs. (*) Quantidade Preço / Ajuste Valor Operação / Ajuste D/C
        # Example:
        # 1-BOVESPA C VISTA PETR4 PETROBRAS PN 100 30,50 3.050,00 D
        
        lines = text.split('\n')
        for line in lines:
            # Regex to catch standard B3 trade line
            # Look for "1-BOVESPA" or similar
            if "1-BOVESPA" in line:
                self._parse_b3_line(line)

    def _parse_b3_line(self, line):
        # This is a hard parsing task due to variable spacing.
        # Strategy: Split by parts
        # C/V is usually the 2nd char after BOVESPA
        try:
            parts = line.split()
            # parts[0] = "1-BOVESPA"
            cv = parts[1] # C or V
            market_type = parts[2] # VISTA, FRACIONARIO
            
            # Ticker is usually parts[3] IF market_type is simple. 
            # Sometimes "VISTA" is followed by Ticker.
            # Let's rely on Ticker pattern (Letters + Number)
            ticker = None
            price = 0.0
            qty = 0
            
            # Find candidate for ticker (e.g., PETR4)
            for p in parts:
                if re.match(r'^[A-Z]{4}(3|4|11)$', p):
                    ticker = p
                    break
            
            # Logic to find numeric values (Qty, Price, Total) implies reading from right to left usually safer
            # Last is D/C
            # 2nd last is Total
            # 3rd last is Price
            # 4th last is Qty
            
            if ticker:
                # Remove D/C if exists
                if parts[-1] in ['D', 'C']:
                    total_str = parts[-2]
                    price_str = parts[-3]
                    qty_str = parts[-4]
                else:
                    total_str = parts[-1]
                    price_str = parts[-2]
                    qty_str = parts[-3]
                
                qty = int(qty_str.replace('.', ''))
                price = float(price_str.replace('.', '').replace(',', '.'))
                total = float(total_str.replace('.', '').replace(',', '.'))
                
                self.transactions.append({
                    "ticker": ticker,
                    "type": "BUY" if cv == 'C' else "SELL",
                    "quantity": qty,
                    "price": price,
                    "total": total
                })
        except Exception as e:
            print(f"Erro parsing line '{line}': {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python ocr_parser.py <caminho_do_pdf>")
    else:
        parser = BrokerageNoteParser(sys.argv[1])
        result = parser.parse()
        if result:
            print("=== NOTA DE CORRETAGEM ===")
            print(f"Data: {result['metadata']['date']}")
            print(f"Corretora: {result['metadata']['broker']}")
            print("\nTransações:")
            for t in result['transactions']:
                print(f"- {t['type']} {t['quantity']}x {t['ticker']} @ R$ {t['price']:.2f}")
