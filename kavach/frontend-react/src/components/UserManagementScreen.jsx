import React, { useState, useEffect } from 'react';
import SovereignSelect from './SovereignSelect';

export default function UserManagementScreen({ user }) {
  const isSuperadmin = user?.role === 'superadmin';
  const userDept = user?.department || 'general';

  const getRoleBadgeStyle = (role) => {
    switch (role) {
      case 'superadmin':
        return { background: '#fef2f2', color: '#991b1b', border: '1px solid #ef4444' };
      case 'admin':
        return { background: '#fffbeb', color: '#b45309', border: '1px solid #f59e0b' };
      case 'approver':
        return { background: '#f5f3ff', color: '#6d28d9', border: '1px solid #8b5cf6' };
      case 'auditor':
        return { background: '#ecfdf5', color: '#047857', border: '1px solid #10b981' };
      default:
        return { background: '#f0f9ff', color: '#0369a1', border: '1px solid #0ea5e9' };
    }
  };

  const [activeTab, setActiveTab] = useState('users'); // 'users' | 'depts_roles'
  const [users, setUsers] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [roles, setRoles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [notice, setNotice] = useState(null); // { type: 'success'|'error', text: '' }

  // Modal states
  const [showProvisionModal, setShowProvisionModal] = useState(false);
  const [provisionData, setProvisionData] = useState({
    name: '',
    email: '',
    password: '',
    role: 'engineer',
    department: isSuperadmin ? 'general' : userDept,
  });

  const [editingUser, setEditingUser] = useState(null);
  const [editData, setEditData] = useState({
    name: '',
    role: '',
    department: '',
    password: '',
  });

  const [deletingUser, setDeletingUser] = useState(null);
  const [deletingDept, setDeletingDept] = useState(null);
  const [deletingRole, setDeletingRole] = useState(null);

  const [showAddDeptModal, setShowAddDeptModal] = useState(false);
  const [newDeptData, setNewDeptData] = useState({ name: '', description: '' });

  const [showAddRoleModal, setShowAddRoleModal] = useState(false);
  const [newRoleData, setNewRoleData] = useState({ name: '', description: '' });

  const [actionLoading, setActionLoading] = useState(false);

  const showNoticeMsg = (type, text) => {
    setNotice({ type, text });
    setTimeout(() => setNotice(null), 5000);
  };

  const loadData = async () => {
    try {
      setLoading(true);
      const [uRes, dRes, rRes] = await Promise.all([
        fetch('/auth/users', { credentials: 'include' }),
        fetch('/auth/departments', { credentials: 'include' }),
        fetch('/auth/roles', { credentials: 'include' }),
      ]);

      if (uRes.ok) setUsers(await uRes.json());
      if (dRes.ok) setDepartments(await dRes.json());
      if (rRes.ok) setRoles(await rRes.json());
    } catch (err) {
      showNoticeMsg('error', `Failed to load management data: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  // Handle Provision User
  const handleProvisionUser = async (e) => {
    e.preventDefault();
    if (!provisionData.name.trim() || !provisionData.email.trim() || !provisionData.password.trim()) {
      showNoticeMsg('error', 'Name, email, and password are required.');
      return;
    }
    setActionLoading(true);
    try {
      const res = await fetch('/auth/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(provisionData),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to provision user');

      showNoticeMsg('success', `User '${data.name}' (${data.email}) provisioned successfully.`);
      setShowProvisionModal(false);
      setProvisionData({ name: '', email: '', password: '', role: 'engineer', department: isSuperadmin ? 'general' : userDept });
      loadData();
    } catch (err) {
      showNoticeMsg('error', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Edit User
  const handleUpdateUser = async (e) => {
    e.preventDefault();
    if (!editingUser) return;
    setActionLoading(true);
    try {
      const payload = {};
      if (editData.name) payload.name = editData.name;
      if (editData.role) payload.role = editData.role;
      if (editData.department) payload.department = editData.department;
      if (editData.password && editData.password.trim()) payload.password = editData.password.trim();

      const res = await fetch(`/auth/users/${editingUser.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to update user');

      showNoticeMsg('success', `User '${data.email}' updated successfully.`);
      setEditingUser(null);
      loadData();
    } catch (err) {
      showNoticeMsg('error', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Delete User Confirmation
  const confirmDeleteUser = async () => {
    if (!deletingUser) return;
    setActionLoading(true);
    try {
      const res = await fetch(`/auth/users/${deletingUser.id}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to delete user');

      showNoticeMsg('success', data.message || `User '${deletingUser.email}' deleted successfully.`);
      setDeletingUser(null);
      loadData();
    } catch (err) {
      showNoticeMsg('error', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Delete Department Confirmation
  const confirmDeleteDepartment = async () => {
    if (!deletingDept) return;
    setActionLoading(true);
    try {
      const res = await fetch(`/auth/departments/${deletingDept.id || deletingDept.name}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to delete department');

      showNoticeMsg('success', data.message || `Department '${deletingDept.name}' deleted.`);
      setDeletingDept(null);
      loadData();
    } catch (err) {
      showNoticeMsg('error', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Delete Role Confirmation
  const confirmDeleteRole = async () => {
    if (!deletingRole) return;
    setActionLoading(true);
    try {
      const res = await fetch(`/auth/roles/${deletingRole.id || deletingRole.name}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to delete role');

      showNoticeMsg('success', data.message || `Role '${deletingRole.name}' deleted.`);
      setDeletingRole(null);
      loadData();
    } catch (err) {
      showNoticeMsg('error', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Add Department
  const handleAddDepartment = async (e) => {
    e.preventDefault();
    if (!newDeptData.name.trim()) return;
    setActionLoading(true);
    try {
      const res = await fetch('/auth/departments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(newDeptData),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to create department');

      showNoticeMsg('success', `Department '${data.name}' added to registry.`);
      setShowAddDeptModal(false);
      setNewDeptData({ name: '', description: '' });
      loadData();
    } catch (err) {
      showNoticeMsg('error', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Handle Add Role
  const handleAddRole = async (e) => {
    e.preventDefault();
    if (!newRoleData.name.trim()) return;
    setActionLoading(true);
    try {
      const res = await fetch('/auth/roles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(newRoleData),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to create role');

      showNoticeMsg('success', `Custom role '${data.name}' added to registry.`);
      setShowAddRoleModal(false);
      setNewRoleData({ name: '', description: '' });
      loadData();
    } catch (err) {
      showNoticeMsg('error', err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const filteredUsers = users.filter((u) => {
    const q = search.toLowerCase().trim();
    if (!q) return true;
    return (
      u.name.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      u.role.toLowerCase().includes(q) ||
      u.department.toLowerCase().includes(q)
    );
  });

  return (
    <section className="screen screen-wide">
      <div className="screen-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h2 className="screen-title" style={{ margin: 0 }}>User & Access Management</h2>
            <span style={{
              fontSize: '11px',
              fontWeight: '700',
              padding: '3px 12px',
              borderRadius: 'var(--radius-pill)',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              background: isSuperadmin ? '#fee2e2' : '#fef3c7',
              color: isSuperadmin ? '#991b1b' : '#92400e',
              border: `1px solid ${isSuperadmin ? '#f87171' : '#f59e0b'}`,
            }}>
              {isSuperadmin ? '★ Sovereign Root Superadmin' : `Dept Admin · ${userDept.toUpperCase()}`}
            </span>
          </div>
          <p className="screen-sub">
            {isSuperadmin
              ? 'Site-wide root authority: cross-department user provisioning, plant topology, and role governance.'
              : `Departmental scope: managing operators, approvers, and engineers strictly within the ${userDept.toUpperCase()} department.`}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            className={`btn ${activeTab === 'users' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveTab('users')}
          >
            Users Directory ({users.length})
          </button>
          <button
            className={`btn ${activeTab === 'depts_roles' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setActiveTab('depts_roles')}
          >
            Departments & Roles ({departments.length}/{roles.length})
          </button>
        </div>
      </div>

      {notice && (
        <div style={{
          padding: '12px 18px',
          borderRadius: 'var(--radius)',
          marginBottom: '16px',
          fontSize: '13px',
          fontWeight: '500',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          background: notice.type === 'success' ? '#ecfdf5' : '#fef2f2',
          border: `1px solid ${notice.type === 'success' ? '#a7f3d0' : '#fecaca'}`,
          color: notice.type === 'success' ? '#065f46' : '#991b1b',
        }}>
          <span>{notice.text}</span>
        </div>
      )}

      {/* TAB 1: USERS DIRECTORY */}
      {activeTab === 'users' && (
        <>
          <div className="filters" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px', gap: '12px' }}>
            <input
              className="field"
              type="search"
              placeholder="Search user by name, email, role, or department…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ flex: 1, maxWidth: '420px', borderRadius: 'var(--radius-pill)', height: '40px', padding: '0 18px' }}
            />
            <button
              className="btn btn-primary"
              onClick={() => setShowProvisionModal(true)}
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <svg className="icon icon-sm" viewBox="0 0 24 24">
                <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <span>Provision User</span>
            </button>
          </div>

          {loading ? (
            <div className="empty">Loading user accounts…</div>
          ) : filteredUsers.length === 0 ? (
            <div className="empty">No matching users found.</div>
          ) : (
            <div style={{
              background: '#ffffff',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              overflow: 'hidden',
              boxShadow: 'var(--shadow-card)',
            }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
                <thead>
                  <tr style={{
                    borderBottom: '1px solid #e2e8f0',
                    background: '#f8fafc',
                    color: '#64748b',
                    textTransform: 'uppercase',
                    fontSize: '11px',
                    letterSpacing: '0.05em',
                  }}>
                    <th style={{ padding: '14px 18px' }}>User</th>
                    <th style={{ padding: '14px 18px' }}>Role</th>
                    <th style={{ padding: '14px 18px' }}>Department</th>
                    <th style={{ padding: '14px 18px' }}>Created</th>
                    <th style={{ padding: '14px 18px', textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.map((u) => {
                    const isSelf = user && (user.id === u.id || user.email === u.email);
                    const isRowAdminOrSuper = u.role === 'admin' || u.role === 'superadmin';
                    const canEdit = isSuperadmin || isSelf || !isRowAdminOrSuper;
                    const canDelete = !isSelf && (isSuperadmin || (!isRowAdminOrSuper && u.department === userDept));

                    return (
                      <tr
                        key={u.id}
                        style={{
                          borderBottom: '1px solid rgba(0, 0, 0, 0.05)',
                          background: '#ffffff',
                          transition: 'background 0.15s ease',
                        }}
                      >
                        <td style={{ padding: '14px 18px' }}>
                          <div style={{ fontWeight: '600', color: '#0f172a' }}>
                            {u.name} {isSelf && <span style={{ fontSize: '10px', color: '#0284c7', border: '1px solid #38bdf8', borderRadius: 'var(--radius-pill)', padding: '2px 8px', marginLeft: '6px', fontWeight: '700', background: '#f0f9ff' }}>YOU</span>}
                          </div>
                          <div style={{ color: '#64748b', fontSize: '12px' }}>{u.email}</div>
                        </td>
                        <td style={{ padding: '14px 18px' }}>
                          <span style={{
                            padding: '3px 10px',
                            borderRadius: 'var(--radius-pill)',
                            fontSize: '11px',
                            fontWeight: '700',
                            textTransform: 'uppercase',
                            ...getRoleBadgeStyle(u.role),
                          }}>
                            {u.role === 'superadmin' ? '★ SUPERADMIN' : u.role}
                          </span>
                        </td>
                        <td style={{ padding: '14px 18px' }}>
                          <span style={{
                            padding: '3px 10px',
                            borderRadius: 'var(--radius-pill)',
                            fontSize: '11px',
                            fontWeight: '600',
                            textTransform: 'uppercase',
                            background: '#f1f5f9',
                            color: '#334155',
                            border: '1px solid #cbd5e1',
                          }}>
                            {u.department}
                          </span>
                        </td>
                        <td style={{ padding: '14px 18px', color: '#64748b', fontSize: '12px' }}>
                          {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                        </td>
                        <td style={{ padding: '14px 18px', textAlign: 'right' }}>
                          <div style={{ display: 'inline-flex', gap: '8px', alignItems: 'center' }}>
                            {canEdit ? (
                              <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => {
                                  setEditingUser(u);
                                  setEditData({ name: u.name, role: u.role, department: u.department, password: '' });
                                }}
                              >
                                Edit
                              </button>
                            ) : null}
                            {canDelete ? (
                              <button
                                className="btn btn-danger-quiet btn-sm"
                                onClick={() => setDeletingUser(u)}
                              >
                                Delete
                              </button>
                            ) : (!isSelf && !isSuperadmin && isRowAdminOrSuper ? (
                              <span style={{ fontSize: '11px', color: '#94a3b8', fontStyle: 'italic', paddingRight: '4px' }}>
                                Admin Protected
                              </span>
                            ) : null)}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* TAB 2: DEPARTMENTS & ROLES */}
      {activeTab === 'depts_roles' && (
        <>
          {!isSuperadmin && (
            <div style={{
              padding: '12px 16px',
              background: '#f8fafc',
              border: '1px solid #cbd5e1',
              borderRadius: '8px',
              marginBottom: '16px',
              fontSize: '13px',
              color: '#475569',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
            }}>
              <svg style={{ width: '18px', height: '18px', color: '#0284c7', flexShrink: 0 }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="16" x2="12" y2="12" />
                <line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
              <span>
                <strong>Department Administrator Scope:</strong> Plant department topology and system roles are managed centrally by the Sovereign Root Superadmin. You have read-only visibility into operational roles.
              </span>
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
            {/* Departments Column */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#0f172a' }}>
                  Plant Departments ({departments.length})
                </h3>
                {isSuperadmin && (
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => setShowAddDeptModal(true)}
                  >
                    + New Department
                  </button>
                )}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {departments.map((d) => (
                  <div
                    key={d.id || d.name}
                    style={{
                      padding: '14px 18px',
                      background: '#ffffff',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius)',
                      boxShadow: 'var(--shadow-soft)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '12px',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: '600', color: '#0284c7', textTransform: 'uppercase', fontSize: '12px', letterSpacing: '0.04em' }}>
                        {d.name}
                      </div>
                      <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                        {d.description || 'No description provided.'}
                      </div>
                    </div>
                    <div>
                      {d.name.toLowerCase() === 'general' ? (
                        <span style={{ fontSize: '10px', color: '#64748b', background: '#f1f5f9', border: '1px solid #cbd5e1', padding: '3px 8px', borderRadius: 'var(--radius-pill)', fontWeight: '700' }}>
                          PROTECTED
                        </span>
                      ) : isSuperadmin ? (
                        <button
                          className="btn btn-danger-quiet btn-sm"
                          onClick={() => setDeletingDept(d)}
                        >
                          Delete
                        </button>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Roles Column */}
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <h3 style={{ fontSize: '16px', fontWeight: '600', color: '#0f172a' }}>
                  System Roles ({roles.length})
                </h3>
                {isSuperadmin && (
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => setShowAddRoleModal(true)}
                  >
                    + New Role
                  </button>
                )}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {roles.map((r) => (
                  <div
                    key={r.id || r.name}
                    style={{
                      padding: '14px 18px',
                      background: '#ffffff',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius)',
                      boxShadow: 'var(--shadow-soft)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: '12px',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: '600', color: '#7e22ce', textTransform: 'uppercase', fontSize: '12px', letterSpacing: '0.04em' }}>
                        {r.name}
                      </div>
                      <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                        {r.description || 'Standard permission tier.'}
                      </div>
                    </div>
                    <div>
                      {['admin', 'superadmin'].includes(r.name.toLowerCase()) ? (
                        <span style={{ fontSize: '10px', color: '#b91c1c', background: '#fee2e2', border: '1px solid #fca5a5', padding: '3px 8px', borderRadius: 'var(--radius-pill)', fontWeight: '700' }}>
                          PROTECTED
                        </span>
                      ) : isSuperadmin ? (
                        <button
                          className="btn btn-danger-quiet btn-sm"
                          onClick={() => setDeletingRole(r)}
                        >
                          Delete
                        </button>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}

      {/* MODAL: PROVISION USER */}
      {showProvisionModal && (
        <div className="auth-overlay" onClick={() => setShowProvisionModal(false)}>
          <div className="auth-card" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '440px', background: '#ffffff', color: '#0f172a' }}>
            <h3 style={{ fontSize: '18px', fontWeight: '600', marginBottom: '4px', color: '#0f172a' }}>
              {isSuperadmin ? 'Provision Enterprise User' : `Provision ${userDept.toUpperCase()} User`}
            </h3>
            <p style={{ fontSize: '12px', color: '#64748b', marginBottom: '16px' }}>
              {isSuperadmin
                ? 'Create a platform account with site-wide role and departmental assignment.'
                : `Provision an operational account strictly within the ${userDept.toUpperCase()} department.`}
            </p>
            <form onSubmit={handleProvisionUser} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div>
                <label style={{ fontSize: '12px', color: '#334155', fontWeight: '500', marginBottom: '4px', display: 'block' }}>Full Name</label>
                <input
                  className="auth-input"
                  style={{ width: '100%', background: '#ffffff', color: '#0f172a', border: '1px solid #cbd5e1' }}
                  type="text"
                  required
                  placeholder="e.g. Rahul Sharma"
                  value={provisionData.name}
                  onChange={(e) => setProvisionData({ ...provisionData, name: e.target.value })}
                />
              </div>

              <div>
                <label style={{ fontSize: '12px', color: '#334155', fontWeight: '500', marginBottom: '4px', display: 'block' }}>Email Address</label>
                <input
                  className="auth-input"
                  style={{ width: '100%', background: '#ffffff', color: '#0f172a', border: '1px solid #cbd5e1' }}
                  type="email"
                  required
                  placeholder="e.g. rahul@mrpl.co.in"
                  value={provisionData.email}
                  onChange={(e) => setProvisionData({ ...provisionData, email: e.target.value })}
                />
              </div>

              <div>
                <label style={{ fontSize: '12px', color: '#334155', fontWeight: '500', marginBottom: '4px', display: 'block' }}>Temporary Password</label>
                <input
                  className="auth-input"
                  style={{ width: '100%', background: '#ffffff', color: '#0f172a', border: '1px solid #cbd5e1' }}
                  type="password"
                  required
                  placeholder="Min 6 characters"
                  value={provisionData.password}
                  onChange={(e) => setProvisionData({ ...provisionData, password: e.target.value })}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '12px', color: '#334155', fontWeight: '500', marginBottom: '4px', display: 'block' }}>Role</label>
                  <SovereignSelect
                    value={provisionData.role}
                    onChange={(e) => setProvisionData({ ...provisionData, role: e.target.value })}
                    options={roles
                      .filter((r) => isSuperadmin || !['admin', 'superadmin'].includes(r.name.toLowerCase()))
                      .map((r) => ({ value: r.name, label: r.name.toUpperCase() }))}
                    placeholder="Select Role"
                    ariaLabel="Select Role"
                  />
                </div>

                <div>
                  <label style={{ fontSize: '12px', color: '#334155', fontWeight: '500', marginBottom: '4px', display: 'block' }}>Department</label>
                  {isSuperadmin ? (
                    <SovereignSelect
                      value={provisionData.department}
                      onChange={(e) => setProvisionData({ ...provisionData, department: e.target.value })}
                      options={departments.map((d) => ({ value: d.name, label: d.name.toUpperCase() }))}
                      placeholder="Select Department"
                      ariaLabel="Select Department"
                    />
                  ) : (
                    <input
                      className="auth-input"
                      style={{ width: '100%', background: '#f1f5f9', color: '#64748b', border: '1px solid #cbd5e1', cursor: 'not-allowed' }}
                      type="text"
                      disabled
                      value={userDept.toUpperCase()}
                    />
                  )}
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '12px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowProvisionModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={actionLoading}>
                  {actionLoading ? 'Provisioning…' : 'Provision User'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: EDIT USER */}
      {editingUser && (
        <div className="auth-overlay" onClick={() => setEditingUser(null)}>
          <div className="auth-card" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '440px', background: '#ffffff', color: '#0f172a' }}>
            <h3 style={{ fontSize: '18px', fontWeight: '600', marginBottom: '4px', color: '#0f172a' }}>
              Edit User: {editingUser.email}
            </h3>
            <p style={{ fontSize: '12px', color: '#64748b', marginBottom: '16px' }}>
              Update assigned role, department, or reset access credentials.
            </p>
            <form onSubmit={handleUpdateUser} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div>
                <label style={{ fontSize: '12px', color: '#334155', fontWeight: '500', marginBottom: '4px', display: 'block' }}>Display Name</label>
                <input
                  className="auth-input"
                  style={{ width: '100%', background: '#ffffff', color: '#0f172a', border: '1px solid #cbd5e1' }}
                  type="text"
                  value={editData.name}
                  onChange={(e) => setEditData({ ...editData, name: e.target.value })}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '12px', color: '#334155', fontWeight: '500', marginBottom: '4px', display: 'block' }}>Role</label>
                  <SovereignSelect
                    value={editData.role}
                    onChange={(e) => setEditData({ ...editData, role: e.target.value })}
                    options={roles
                      .filter((r) => isSuperadmin || !['admin', 'superadmin'].includes(r.name.toLowerCase()))
                      .map((r) => ({ value: r.name, label: r.name.toUpperCase() }))}
                    placeholder="Select Role"
                    ariaLabel="Select Role"
                  />
                </div>

                <div>
                  <label style={{ fontSize: '12px', color: '#334155', fontWeight: '500', marginBottom: '4px', display: 'block' }}>Department</label>
                  {isSuperadmin ? (
                    <SovereignSelect
                      value={editData.department}
                      onChange={(e) => setEditData({ ...editData, department: e.target.value })}
                      options={departments.map((d) => ({ value: d.name, label: d.name.toUpperCase() }))}
                      placeholder="Select Department"
                      ariaLabel="Select Department"
                    />
                  ) : (
                    <input
                      className="auth-input"
                      style={{ width: '100%', background: '#f1f5f9', color: '#64748b', border: '1px solid #cbd5e1', cursor: 'not-allowed' }}
                      type="text"
                      disabled
                      value={(editData.department || userDept).toUpperCase()}
                    />
                  )}
                </div>
              </div>

              <div>
                <label style={{ fontSize: '12px', color: '#334155', fontWeight: '500', marginBottom: '4px', display: 'block' }}>
                  Reset Password (leave blank to keep current)
                </label>
                <input
                  className="auth-input"
                  style={{ width: '100%', background: '#ffffff', color: '#0f172a', border: '1px solid #cbd5e1' }}
                  type="password"
                  placeholder="New password (optional)"
                  value={editData.password}
                  onChange={(e) => setEditData({ ...editData, password: e.target.value })}
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '12px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setEditingUser(null)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={actionLoading}>
                  {actionLoading ? 'Saving…' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: CONFIRM DELETE USER */}
      {deletingUser && (
        <div className="confirm-overlay" onClick={() => !actionLoading && setDeletingUser(null)}>
          <div
            className="confirm-modal"
            onClick={(e) => e.stopPropagation()}
            style={{
              maxWidth: '440px',
              background: '#ffffff',
              borderRadius: 'var(--radius-xl)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              boxShadow: 'var(--shadow-modal)',
              padding: '28px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '8px' }}>
              <div style={{
                width: '46px',
                height: '46px',
                borderRadius: 'var(--radius-pill)',
                background: '#fee2e2',
                border: '1px solid #fca5a5',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#dc2626',
                flexShrink: 0,
              }}>
                <svg viewBox="0 0 24 24" style={{ width: '22px', height: '22px', stroke: 'currentColor', fill: 'none', strokeWidth: '2', strokeLinecap: 'round', strokeLinejoin: 'round' }}>
                  <path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                </svg>
              </div>
              <div>
                <h3 style={{ fontSize: '18px', fontWeight: '700', color: '#0f172a', margin: 0 }}>
                  Confirm User Deletion
                </h3>
                <p style={{ fontSize: '12px', color: '#dc2626', margin: '2px 0 0 0', fontWeight: '600' }}>
                  Permanent Action · Cannot be Undone
                </p>
              </div>
            </div>

            <div style={{
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: 'var(--radius)',
              padding: '14px 16px',
              fontSize: '13px',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              margin: '14px 0',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>Account Name:</span>
                <span style={{ fontWeight: '600', color: '#0f172a' }}>{deletingUser.name}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>Email Address:</span>
                <span style={{ color: '#334155' }}>{deletingUser.email}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>Role & Department:</span>
                <span style={{ textTransform: 'uppercase', fontSize: '11px', fontWeight: '700', letterSpacing: '0.04em', color: '#0284c7' }}>
                  {deletingUser.role} · {deletingUser.department}
                </span>
              </div>
            </div>

            <p style={{ fontSize: '13px', color: '#475569', lineHeight: '1.5', margin: '0 0 16px' }}>
              Are you sure you want to permanently delete user <strong style={{ color: '#0f172a' }}>{deletingUser.email}</strong>? They will be immediately disconnected and prevented from logging in.
            </p>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setDeletingUser(null)}
                disabled={actionLoading}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={confirmDeleteUser}
                disabled={actionLoading}
              >
                {actionLoading ? 'Deleting…' : 'Yes, Delete User'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: ADD DEPARTMENT */}
      {showAddDeptModal && (
        <div className="auth-overlay" onClick={() => setShowAddDeptModal(false)}>
          <div className="auth-card" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '400px', background: '#ffffff', color: '#0f172a' }}>
            <h3 style={{ fontSize: '18px', fontWeight: '600', marginBottom: '12px', color: '#0f172a' }}>
              Add Plant Department
            </h3>
            <form onSubmit={handleAddDepartment} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div>
                <label style={{ fontSize: '12px', color: '#334155', fontWeight: '500', marginBottom: '4px', display: 'block' }}>Department Identifier</label>
                <input
                  className="auth-input"
                  style={{ width: '100%', background: '#ffffff', color: '#0f172a', border: '1px solid #cbd5e1' }}
                  type="text"
                  required
                  placeholder="e.g. instrumentation, electrical"
                  value={newDeptData.name}
                  onChange={(e) => setNewDeptData({ ...newDeptData, name: e.target.value })}
                />
              </div>
              <div>
                <label style={{ fontSize: '12px', color: '#334155', fontWeight: '500', marginBottom: '4px', display: 'block' }}>Description</label>
                <input
                  className="auth-input"
                  style={{ width: '100%', background: '#ffffff', color: '#0f172a', border: '1px solid #cbd5e1' }}
                  type="text"
                  placeholder="Description of plant operations"
                  value={newDeptData.description}
                  onChange={(e) => setNewDeptData({ ...newDeptData, description: e.target.value })}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '8px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowAddDeptModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={actionLoading}>
                  {actionLoading ? 'Adding…' : 'Add Department'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: ADD ROLE */}
      {showAddRoleModal && (
        <div className="auth-overlay" onClick={() => setShowAddRoleModal(false)}>
          <div className="auth-card" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '400px', background: '#ffffff', color: '#0f172a' }}>
            <h3 style={{ fontSize: '18px', fontWeight: '600', marginBottom: '12px', color: '#0f172a' }}>
              Add Operational Role
            </h3>
            <form onSubmit={handleAddRole} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div>
                <label style={{ fontSize: '12px', color: '#334155', fontWeight: '500', marginBottom: '4px', display: 'block' }}>Role Identifier</label>
                <input
                  className="auth-input"
                  style={{ width: '100%', background: '#ffffff', color: '#0f172a', border: '1px solid #cbd5e1' }}
                  type="text"
                  required
                  placeholder="e.g. shift_supervisor, inspector"
                  value={newRoleData.name}
                  onChange={(e) => setNewRoleData({ ...newRoleData, name: e.target.value })}
                />
              </div>
              <div>
                <label style={{ fontSize: '12px', color: '#334155', fontWeight: '500', marginBottom: '4px', display: 'block' }}>Description</label>
                <input
                  className="auth-input"
                  style={{ width: '100%', background: '#ffffff', color: '#0f172a', border: '1px solid #cbd5e1' }}
                  type="text"
                  placeholder="Responsibility description"
                  value={newRoleData.description}
                  onChange={(e) => setNewRoleData({ ...newRoleData, description: e.target.value })}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '8px' }}>
                <button type="button" className="btn btn-secondary" onClick={() => setShowAddRoleModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={actionLoading}>
                  {actionLoading ? 'Adding…' : 'Add Role'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL: CONFIRM DELETE DEPARTMENT */}
      {deletingDept && (
        <div className="confirm-overlay" onClick={() => !actionLoading && setDeletingDept(null)}>
          <div
            className="confirm-modal"
            onClick={(e) => e.stopPropagation()}
            style={{
              maxWidth: '440px',
              background: '#ffffff',
              borderRadius: 'var(--radius-xl)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              boxShadow: 'var(--shadow-modal)',
              padding: '28px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '8px' }}>
              <div style={{
                width: '46px',
                height: '46px',
                borderRadius: 'var(--radius-pill)',
                background: '#fee2e2',
                border: '1px solid #fca5a5',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#dc2626',
                flexShrink: 0,
              }}>
                <svg viewBox="0 0 24 24" style={{ width: '22px', height: '22px', stroke: 'currentColor', fill: 'none', strokeWidth: '2', strokeLinecap: 'round', strokeLinejoin: 'round' }}>
                  <path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                </svg>
              </div>
              <div>
                <h3 style={{ fontSize: '18px', fontWeight: '700', color: '#0f172a', margin: 0 }}>
                  Confirm Department Deletion
                </h3>
                <p style={{ fontSize: '12px', color: '#dc2626', margin: '2px 0 0 0', fontWeight: '600' }}>
                  Permanent Action · Cannot be Undone
                </p>
              </div>
            </div>

            <div style={{
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: 'var(--radius)',
              padding: '14px 16px',
              fontSize: '13px',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              margin: '14px 0',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>Department:</span>
                <span style={{ fontWeight: '600', color: '#0f172a', textTransform: 'uppercase' }}>{deletingDept.name}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>Description:</span>
                <span style={{ color: '#334155' }}>{deletingDept.description || '—'}</span>
              </div>
            </div>

            <p style={{ fontSize: '13px', color: '#475569', lineHeight: '1.5', margin: '0 0 16px' }}>
              Are you sure you want to remove the <strong style={{ color: '#0f172a', textTransform: 'uppercase' }}>{deletingDept.name}</strong> department?
              If any active users are currently assigned to this department, deletion will be blocked until they are reassigned.
            </p>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setDeletingDept(null)}
                disabled={actionLoading}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={confirmDeleteDepartment}
                disabled={actionLoading}
              >
                {actionLoading ? 'Deleting…' : 'Delete Department'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: CONFIRM DELETE ROLE */}
      {deletingRole && (
        <div className="confirm-overlay" onClick={() => !actionLoading && setDeletingRole(null)}>
          <div
            className="confirm-modal"
            onClick={(e) => e.stopPropagation()}
            style={{
              maxWidth: '440px',
              background: '#ffffff',
              borderRadius: 'var(--radius-xl)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              boxShadow: 'var(--shadow-modal)',
              padding: '28px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '8px' }}>
              <div style={{
                width: '46px',
                height: '46px',
                borderRadius: 'var(--radius-pill)',
                background: '#fee2e2',
                border: '1px solid #fca5a5',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#dc2626',
                flexShrink: 0,
              }}>
                <svg viewBox="0 0 24 24" style={{ width: '22px', height: '22px', stroke: 'currentColor', fill: 'none', strokeWidth: '2', strokeLinecap: 'round', strokeLinejoin: 'round' }}>
                  <path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                </svg>
              </div>
              <div>
                <h3 style={{ fontSize: '18px', fontWeight: '700', color: '#0f172a', margin: 0 }}>
                  Confirm Role Deletion
                </h3>
                <p style={{ fontSize: '12px', color: '#dc2626', margin: '2px 0 0 0', fontWeight: '600' }}>
                  Permanent Action · Cannot be Undone
                </p>
              </div>
            </div>

            <div style={{
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: 'var(--radius)',
              padding: '14px 16px',
              fontSize: '13px',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
              margin: '14px 0',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>Role:</span>
                <span style={{ fontWeight: '600', color: '#0f172a', textTransform: 'uppercase' }}>{deletingRole.name}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#64748b' }}>Description:</span>
                <span style={{ color: '#334155' }}>{deletingRole.description || '—'}</span>
              </div>
            </div>

            <p style={{ fontSize: '13px', color: '#475569', lineHeight: '1.5', margin: '0 0 16px' }}>
              Are you sure you want to remove the <strong style={{ color: '#0f172a', textTransform: 'uppercase' }}>{deletingRole.name}</strong> role?
              If any active users currently hold this role, deletion will be blocked until they are reassigned.
            </p>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setDeletingRole(null)}
                disabled={actionLoading}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={confirmDeleteRole}
                disabled={actionLoading}
              >
                {actionLoading ? 'Deleting…' : 'Delete Role'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
