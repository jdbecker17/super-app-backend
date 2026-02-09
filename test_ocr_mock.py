import unittest
from unittest.mock import MagicMock, patch
from ocr_parser import BrokerageNoteParser

# Simulando o texto de uma nota SINACUR (XP Investimentos)
MOCK_PDF_TEXT = """
                                NOTA DE NEGOCIAÇÃO                                
                                                                        Data pregão
                                                                        15/08/2025
XP INVESTIMENTOS CCTVM S.A.
...
Q Negociação C/V Tipo mercado Prazo Especificação do título Obs. (*) Quantidade Preço / Ajuste Valor Operação / Ajuste D/C
1-BOVESPA C VISTA PETR4 PETROBRAS PN 100 30,50 3.050,00 D
1-BOVESPA V VISTA VALE3 VALE ON 50 68,00 3.400,00 C
...
"""

class TestOCR(unittest.TestCase):
    @patch('ocr_parser.pdfplumber.open')
    def test_parse_xp_note(self, mock_open):
        # Setup Mock
        mock_page = MagicMock()
        mock_page.extract_text.return_value = MOCK_PDF_TEXT
        
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__.return_value = mock_pdf
        
        # When pdfplumber.open(...) is called, return mock_pdf
        mock_open.return_value = mock_pdf
        
        # Run Parser with ANY path (mock intercepts it)
        parser = BrokerageNoteParser("dummy.pdf")
        result = parser.parse()
        
        # Verify Metadata
        self.assertEqual(result['metadata']['date'], "15/08/2025")
        self.assertEqual(result['metadata']['broker'], "XP")
        
        # Verify Transactions
        txs = result['transactions']
        self.assertEqual(len(txs), 2)
        
        # Transaction 1: Buy PETR4
        self.assertEqual(txs[0]['ticker'], "PETR4")
        self.assertEqual(txs[0]['type'], "BUY")
        self.assertEqual(txs[0]['quantity'], 100)
        self.assertEqual(txs[0]['price'], 30.50)
        self.assertEqual(txs[0]['total'], 3050.00)
        
        # Transaction 2: Sell VALE3
        self.assertEqual(txs[1]['ticker'], "VALE3")
        self.assertEqual(txs[1]['type'], "SELL")
        self.assertEqual(txs[1]['quantity'], 50)
        self.assertEqual(txs[1]['price'], 68.00)
        self.assertEqual(txs[1]['total'], 3400.00)

if __name__ == '__main__':
    unittest.main()
