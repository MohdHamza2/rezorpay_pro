import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './contexts/AuthContext';
import { AuthGuard } from './components/AuthGuard';
import { Login } from './pages/Login';
import { Register } from './pages/Register';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { Clients } from './pages/Clients';
import { ArStatement } from './pages/ArStatement';
import { Quotations } from './pages/Quotations';
import { QuotationForm } from './pages/QuotationForm';
import { QuotationDetail } from './pages/QuotationDetail';
import { Lpos } from './pages/Lpos';
import { LpoForm } from './pages/LpoForm';
import { LpoDetail } from './pages/LpoDetail';
import { DeliveryNotes } from './pages/DeliveryNotes';
import { DeliveryNoteForm } from './pages/DeliveryNoteForm';
import { DeliveryNoteDetail } from './pages/DeliveryNoteDetail';
import { CreditNotes } from './pages/CreditNotes';
import { CreditNoteForm } from './pages/CreditNoteForm';
import { CreditNoteDetail } from './pages/CreditNoteDetail';
import { Invoices } from './pages/Invoices';
import { Settings } from './pages/Settings';
import { Products } from './pages/Products';
import { Suppliers } from './pages/Suppliers';
import { Inventory } from './pages/Inventory';
import { Procurement } from './pages/Procurement';
import { RFQMaster } from './pages/RFQ';
import { PurchaseOrders } from './pages/SPO';
import { SPOBuilder } from './pages/SPOBuilder';
import { SPODetail } from './pages/SPODetail';
import { GoodsReceiptNotes } from './pages/GRN';
import { GRNDetail } from './pages/GRNDetail';
import { SupplierInvoices } from './pages/SupplierInvoices';
import { SupplierInvoiceDetail } from './pages/SupplierInvoiceDetail';
import { Toaster } from 'react-hot-toast';

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Toaster position="top-right" />
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            {/* Public routes */}
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />

            {/* Protected routes */}
            <Route
              path="/"
              element={
                <AuthGuard>
                  <Layout />
                </AuthGuard>
              }
            >
              <Route index element={<Dashboard />} />
              <Route path="clients" element={<Clients />} />
              <Route path="clients/:id/statement" element={<ArStatement />} />
              <Route path="quotations" element={<Quotations />} />
              <Route path="quotations/new" element={<QuotationForm />} />
              <Route path="quotations/:id/edit" element={<QuotationForm />} />
              <Route path="quotations/:id" element={<QuotationDetail />} />
              <Route path="lpos" element={<Lpos />} />
              <Route path="lpos/new" element={<LpoForm />} />
              <Route path="lpos/:id/edit" element={<LpoForm />} />
              <Route path="lpos/:id" element={<LpoDetail />} />
              <Route path="delivery-notes" element={<DeliveryNotes />} />
              <Route path="delivery-notes/new" element={<DeliveryNoteForm />} />
              <Route path="delivery-notes/:id/edit" element={<DeliveryNoteForm />} />
              <Route path="delivery-notes/:id" element={<DeliveryNoteDetail />} />
              <Route path="credit-notes" element={<CreditNotes />} />
              <Route path="credit-notes/new" element={<CreditNoteForm />} />
              <Route path="credit-notes/:id/edit" element={<CreditNoteForm />} />
              <Route path="credit-notes/:id" element={<CreditNoteDetail />} />
              <Route path="invoices" element={<Invoices />} />
              <Route path="settings" element={<Settings />} />
              <Route path="products" element={<Products />} />
              <Route path="suppliers" element={<Suppliers />} />
              <Route path="inventory" element={<Inventory />} />
              <Route path="procurement" element={<Procurement />} />
              <Route path="rfq" element={<RFQMaster />} />
              <Route path="spo" element={<PurchaseOrders />} />
              <Route path="spo/new" element={<SPOBuilder />} />
              <Route path="spo/:id" element={<SPODetail />} />
              <Route path="grn" element={<GoodsReceiptNotes />} />
              <Route path="grn/:id" element={<GRNDetail />} />
              <Route path="supplier-invoices" element={<SupplierInvoices />} />
              <Route path="supplier-invoices/:id" element={<SupplierInvoiceDetail />} />
            </Route>

            {/* Catch-all redirect */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
