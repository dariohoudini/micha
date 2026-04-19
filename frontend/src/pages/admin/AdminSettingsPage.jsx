import { useState } from 'react'
import AdminLayout, { ADMIN_COLORS } from '@/layouts/AdminLayout'

export default function AdminSettingsPage() {
  const [toast, setToast] = useState(null)
  const [settings, setSettings] = useState({
    commission_rate: '5',
    min_withdrawal: '1000',
    max_withdrawal: '500000',
    withdrawal_days: '1-2',
    express_coverage: 'Luanda',
    maintenance_mode: false,
    new_registrations: true,
    seller_auto_approve: false,
    product_auto_approve: false,
    max_products_per_seller: '500',
    platform_name: 'MICHA Express',
    support_email: 'suporte@micha.ao',
    support_phone: '+244 923 000 000',
  })
  const [activeTab, setActiveTab] = useState('financial')

  const showToast = (msg) => {
    setToast(msg)
    setTimeout(() => setToast(null), 2500)
  }

  const handleChange = (key, value) => setSettings(s => ({ ...s, [key]: value }))

  const handleSave = async () => {
    await new Promise(r => setTimeout(r, 600))
    showToast('Configurações guardadas com sucesso!')
  }

  const Toggle = ({ settingKey, label, sub, danger = false }) => (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: ADMIN_COLORS.surface, borderRadius: 12, border: `1px solid ${danger && settings[settingKey] ? 'rgba(239,68,68,0.3)' : ADMIN_COLORS.border}`, padding: '14px 16px' }}>
      <div>
        <p style={{ fontSize: 14, fontWeight: 500, color: danger && settings[settingKey] ? '#ef4444' : ADMIN_COLORS.text }}>{label}</p>
        {sub && <p style={{ fontSize: 11, color: ADMIN_COLORS.muted, marginTop: 2 }}>{sub}</p>}
      </div>
      <div onClick={() => handleChange(settingKey, !settings[settingKey])}
        style={{ width: 44, height: 24, borderRadius: 12, background: settings[settingKey] ? (danger ? '#ef4444' : '#6366f1') : ADMIN_COLORS.border, position: 'relative', cursor: 'pointer', transition: 'background 0.2s', flexShrink: 0 }}>
        <div style={{ position: 'absolute', top: 3, left: settings[settingKey] ? 23 : 3, width: 18, height: 18, borderRadius: '50%', background: '#FFFFFF', transition: 'left 0.2s', boxShadow: '0 1px 4px rgba(0,0,0,0.3)' }} />
      </div>
    </div>
  )

  const Field = ({ label, settingKey, type = 'text', placeholder, hint }) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label style={{ fontSize: 12, fontWeight: 500, color: ADMIN_COLORS.muted, letterSpacing: '0.05em', textTransform: 'uppercase' }}>{label}</label>
      <input type={type} value={settings[settingKey]} onChange={e => handleChange(settingKey, e.target.value)} placeholder={placeholder}
        style={{ background: ADMIN_COLORS.surface, border: `1px solid ${ADMIN_COLORS.border}`, borderRadius: 12, padding: '11px 14px', color: ADMIN_COLORS.text, fontSize: 13, outline: 'none', fontFamily: "'DM Sans', sans-serif" }} />
      {hint && <p style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>{hint}</p>}
    </div>
  )

  const TABS = [
    { v: 'financial', l: 'Financeiro' },
    { v: 'platform', l: 'Plataforma' },
    { v: 'access', l: 'Acesso' },
    { v: 'support', l: 'Suporte' },
  ]

  return (
    <AdminLayout title="Configurações">
      {toast && (
        <div style={{ position: 'fixed', top: 60, left: '50%', transform: 'translateX(-50%)', zIndex: 999, background: '#059669', color: '#FFFFFF', padding: '10px 20px', borderRadius: 12, fontSize: 13, fontWeight: 500, boxShadow: '0 4px 20px rgba(0,0,0,0.4)', whiteSpace: 'nowrap' }}>{toast}</div>
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', padding: '0 16px', gap: 0, borderBottom: `1px solid ${ADMIN_COLORS.border}`, flexShrink: 0 }}>
        {TABS.map(tab => (
          <button key={tab.v} onClick={() => setActiveTab(tab.v)}
            style={{ flex: 1, padding: '12px 0', background: 'none', border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: activeTab === tab.v ? 600 : 400, color: activeTab === tab.v ? '#818cf8' : ADMIN_COLORS.muted, borderBottom: `2px solid ${activeTab === tab.v ? '#6366f1' : 'transparent'}`, marginBottom: -1 }}>
            {tab.l}
          </button>
        ))}
      </div>

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: 14 }}>

          {/* FINANCIAL */}
          {activeTab === 'financial' && <>
            <div style={{ background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 12, padding: '12px 14px' }}>
              <p style={{ fontSize: 12, color: '#818cf8', fontWeight: 600, marginBottom: 4 }}>💡 Configurações financeiras</p>
              <p style={{ fontSize: 12, color: ADMIN_COLORS.muted, lineHeight: 1.5 }}>Alterações às taxas aplicam-se a novos pedidos. Pedidos em curso não são afectados.</p>
            </div>
            <Field label="Taxa de comissão (%)" settingKey="commission_rate" type="number" hint="Aplicada sobre o valor total de cada venda. Actualmente: 5%" />
            <Field label="Levantamento mínimo (Kz)" settingKey="min_withdrawal" type="number" hint="Valor mínimo que um vendedor pode levantar." />
            <Field label="Levantamento máximo (Kz)" settingKey="max_withdrawal" type="number" hint="Limite por transacção de levantamento." />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <label style={{ fontSize: 12, fontWeight: 500, color: ADMIN_COLORS.muted, letterSpacing: '0.05em', textTransform: 'uppercase' }}>Prazo de pagamento</label>
              <select value={settings.withdrawal_days} onChange={e => handleChange('withdrawal_days', e.target.value)}
                style={{ background: ADMIN_COLORS.surface, border: `1px solid ${ADMIN_COLORS.border}`, borderRadius: 12, padding: '11px 14px', color: ADMIN_COLORS.text, fontSize: 13, outline: 'none', appearance: 'none', fontFamily: "'DM Sans', sans-serif", cursor: 'pointer' }}>
                {['Mesmo dia', '1-2', '2-3', '3-5'].map(v => <option key={v} value={v}>{v === 'Mesmo dia' ? v : `${v} dias úteis`}</option>)}
              </select>
            </div>
          </>}

          {/* PLATFORM */}
          {activeTab === 'platform' && <>
            <Field label="Nome da plataforma" settingKey="platform_name" />
            <Field label="Cobertura Express" settingKey="express_coverage" hint="Províncias onde a entrega express está disponível." />
            <Field label="Máx. produtos por vendedor" settingKey="max_products_per_seller" type="number" />
            <Toggle settingKey="maintenance_mode" label="Modo de manutenção" sub="Desactiva o acesso para todos os utilizadores" danger />
            <Toggle settingKey="product_auto_approve" label="Aprovar produtos automaticamente" sub="Produtos publicam sem revisão manual" />
            <Toggle settingKey="seller_auto_approve" label="Aprovar vendedores automaticamente" sub="Candidaturas aprovadas sem revisão" />
          </>}

          {/* ACCESS */}
          {activeTab === 'access' && <>
            <Toggle settingKey="new_registrations" label="Permitir novos registos" sub="Novos utilizadores podem criar conta" />
            <div style={{ background: ADMIN_COLORS.card, borderRadius: 14, border: `1px solid ${ADMIN_COLORS.border}`, padding: 16 }}>
              <h3 style={{ fontSize: 13, fontWeight: 600, color: ADMIN_COLORS.text, marginBottom: 12 }}>Sessões activas</h3>
              {[{ user: 'Admin Principal', device: 'MacBook Air · Luanda', time: 'Agora' }, { user: 'Moderador', device: 'iPhone · Luanda', time: '2h atrás' }].map((session, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: i === 0 ? `1px solid ${ADMIN_COLORS.border}` : 'none' }}>
                  <div>
                    <p style={{ fontSize: 13, color: ADMIN_COLORS.text, fontWeight: 500 }}>{session.user}</p>
                    <p style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>{session.device}</p>
                  </div>
                  <span style={{ fontSize: 11, color: ADMIN_COLORS.muted }}>{session.time}</span>
                </div>
              ))}
            </div>
            <div style={{ background: 'rgba(239,68,68,0.08)', borderRadius: 14, border: '1px solid rgba(239,68,68,0.2)', padding: 16 }}>
              <h3 style={{ fontSize: 13, fontWeight: 600, color: '#ef4444', marginBottom: 8 }}>Zona de perigo</h3>
              <button style={{ width: '100%', padding: '12px 0', borderRadius: 10, border: '1px solid rgba(239,68,68,0.3)', background: 'rgba(239,68,68,0.1)', fontSize: 13, color: '#ef4444', cursor: 'pointer' }}>
                Encerrar todas as sessões
              </button>
            </div>
          </>}

          {/* SUPPORT */}
          {activeTab === 'support' && <>
            <Field label="Email de suporte" settingKey="support_email" type="email" />
            <Field label="Telefone de suporte" settingKey="support_phone" />
            <div style={{ background: ADMIN_COLORS.card, borderRadius: 14, border: `1px solid ${ADMIN_COLORS.border}`, padding: 16 }}>
              <h3 style={{ fontSize: 13, fontWeight: 600, color: ADMIN_COLORS.text, marginBottom: 12 }}>Estatísticas de suporte</h3>
              {[{ l: 'Tickets abertos', v: '12' }, { l: 'Tempo médio de resposta', v: '4h 23m' }, { l: 'Satisfação', v: '94%' }, { l: 'Resolvidos hoje', v: '8' }].map(stat => (
                <div key={stat.l} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: `1px solid ${ADMIN_COLORS.border}` }}>
                  <span style={{ fontSize: 13, color: ADMIN_COLORS.muted }}>{stat.l}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: ADMIN_COLORS.text }}>{stat.v}</span>
                </div>
              ))}
            </div>
          </>}

          <button onClick={handleSave}
            style={{ width: '100%', padding: '1rem', borderRadius: '1rem', background: '#6366f1', border: 'none', fontSize: 15, fontWeight: 600, color: '#FFFFFF', cursor: 'pointer', marginTop: 4 }}>
            Guardar configurações
          </button>
        </div>
      </div>
    </AdminLayout>
  )
}
