import { Outlet, Link, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import styles from './Layout.module.css';
import { LayoutDashboard, Users, FileText, LogOut, Settings as SettingsIcon, Package, Truck, Boxes, ShoppingCart, SendToBack, FileSignature, ClipboardCheck } from 'lucide-react';

export const Layout = () => {
  const { user, logout } = useAuth();
  const location = useLocation();

  const handleLogout = () => {
    logout();
  };

  const navGroups = [
    {
      title: 'Overview',
      items: [
        { path: '/', label: 'Dashboard', icon: LayoutDashboard },
      ]
    },
    {
      title: 'Sales & Customers',
      items: [
        { path: '/clients', label: 'Clients', icon: Users },
        { path: '/invoices', label: 'Invoices', icon: FileText },
      ]
    },
    {
      title: 'Purchasing & Suppliers',
      items: [
        { path: '/suppliers', label: 'Suppliers', icon: Truck },
        { path: '/procurement', label: 'Procurement', icon: ShoppingCart },
        { path: '/rfq', label: 'Sourcing (RFQ)', icon: SendToBack },
        { path: '/spo', label: 'Purchase Orders', icon: FileSignature },
        { path: '/grn', label: 'Inbound Shipments', icon: ClipboardCheck },
        { path: '/supplier-invoices', label: 'AP Payables', icon: FileText },
      ]
    },
    {
      title: 'Inventory Management',
      items: [
        { path: '/products', label: 'Products', icon: Package },
        { path: '/inventory', label: 'Inventory', icon: Boxes },
      ]
    },
    {
      title: 'System',
      items: [
        { path: '/settings', label: 'Settings', icon: SettingsIcon },
      ]
    }
  ];

  return (
    <div className={styles.layout}>
      <aside className={styles.sidebar}>
        <div className={styles.logo}>
          <h2>InvoiceSaaS</h2>
        </div>
        <nav className={styles.nav}>
          {navGroups.map((group) => (
            <div key={group.title} className={styles.navGroup}>
              <h4 className={styles.navGroupTitle}>{group.title}</h4>
              {group.items.map((item) => {
                const Icon = item.icon;
                const isActive = location.pathname === item.path || (item.path !== '/' && location.pathname.startsWith(item.path));
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={`${styles.navItem} ${isActive ? styles.active : ''}`}
                  >
                    <Icon size={18} />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <div className={styles.userSection}>
          <div className={styles.userInfo}>
            <p className={styles.userName}>{user?.name}</p>
            <p className={styles.userEmail}>{user?.email}</p>
          </div>
          <button className={styles.logoutBtn} onClick={handleLogout}>
            <LogOut size={20} />
            <span>Logout</span>
          </button>
        </div>
      </aside>
      <main className={styles.main}>
        <div className={styles.header}>
          <h3>Workspace</h3>
        </div>
        <div className={styles.content}>
          <Outlet />
        </div>
      </main>
    </div>
  );
};
