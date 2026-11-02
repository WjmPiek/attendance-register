import DocumentUploaders from '../components/DocumentUploaders'
import RemovalSettings from '../components/RemovalSettings'
import CommissionDeliverySettings from '../components/CommissionDeliverySettings'
import ReceiptSettings from '../components/ReceiptSettings'

export default function CommissionSettingsPage() {
  return <section className="mortuary-book commission-settings">
    <header className="form-card"><h1>Commissions</h1><p>Configure commission fees, document uploaders, branch VAT and the monthly finance email.</p></header>
    <RemovalSettings />
    <DocumentUploaders />
    <ReceiptSettings />
    <CommissionDeliverySettings />
  </section>
}
