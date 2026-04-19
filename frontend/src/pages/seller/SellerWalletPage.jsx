import { useState } from 'react'
import SellerLayout from '@/layouts/SellerLayout'
import { formatPrice } from '@/components/buyer/mockData'

const TRANSACTIONS = [
  { id: 't1', type: 'sale',        label: 'Venda — Vestido Capulana ×2',    amount: 17000,  fee: -850,   date: '13 Abr 09:32', status: 'completed', orderId: 'ORD-001' },
  { id: 't2', type: 'sale',        label: 'Venda — Colar de Missangas',     amount: 4500,   fee: -225,   date: '12 Abr 14:15', status: 'completed', orderId: 'ORD-002' },
  { id: 't3', type: 'withdrawal',  label: 'Levantamento — Multicaixa',      amount: -15000, fee: 0,      date: '10 Abr 11:00', status: 'completed', orderId: null },
  { id: 't4', type: 'sale',        label: 'Venda — Bolsa de Couro',         amount: 28000,  fee: -1400,  date: '09 Abr 16:20', status: 'completed', orderId: 'ORD-004' },
  { id: 't5', type: 'pending',     label: 'Venda pendente — Vestido ×1',   amount: 8500,   fee: -425,   date: '13 Abr 16:00', status: 'pending',   orderId: 'ORD-005' },
  { id: 't6', type: 'refund',      label: 'Reembolso — Pedido cancelado',  amount: -4500,  fee: 225,    date: '08 Abr 09:15', status: 'completed', orderId: null },
]

const COMMISSION_RATE = 0.05 // 5%

export default function SellerWalletPage() {
  const [showWithdraw, setShowWithdraw] = useState(false)
  const [withdrawStep, setWithdrawStep] = useState(1) // 1: amount, 2: confirm, 3: success
  const [withdrawAmount, setWithdrawAmount] = useState('')
  const [phone, setPhone] = useState('')
  const [phoneError, setPhoneError] = useState('')
  const [amountError, setAmountError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showBalance, setShowBalance] = useState(true)

  const available = 34025
  const pending = 8075 // after commission
  const totalEarned = 49025
  const totalWithdrawn = 15000
  const totalCommissions = 2900

  const validateWithdraw = () => {
    let valid = true
    if (!withdrawAmount || isNaN(withdrawAmount) || Number(withdrawAmount) <= 0) {
      setAmountError('Insira um valor válido')
      valid = false
    } else if (Number(withdrawAmount) > available) {
      setAmountError(`Máximo disponível: ${formatPrice(available)}`)
      valid = false
    } else if (Number(withdrawAmount) < 1000) {
      setAmountError('Mínimo de levantamento: 1 000 Kz')
      valid = false
    } else {
      setAmountError('')
    }
    if (!phone || phone.replace(/\s/g, '').length < 9) {
      setPhoneError('Insira um número válido')
      valid = false
    } else {
      setPhoneError('')
    }
    return valid
  }

  const handleWithdraw = async () => {
    if (!validateWithdraw()) return
    setLoading(true)
    await new Promise(r => setTimeout(r, 1500))
    setLoading(false)
    setWithdrawStep(3)
  }

  const resetWithdraw = () => {
    setShowWithdraw(false)
    setWithdrawStep(1)
    setWithdrawAmount('')
    setPhone('')
    setAmountError('')
    setPhoneError('')
  }

  const TypeIcon = ({ type, amount }) => {
    const configs = {
      sale:       { color: '#059669', bg: 'rgba(5,150,105,0.1)',    icon: 'M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5' },
      withdrawal: { color: '#3b82f6', bg: 'rgba(59,130,246,0.1)',   icon: 'M5 12h14M12 5l7 7-7 7' },
      pending:    { color: '#f59e0b', bg: 'rgba(245,158,11,0.1)',   icon: 'M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83' },
      refund:     { color: '#dc2626', bg: 'rgba(220,38,38,0.1)',    icon: 'M19 12H5M12 5l-7 7 7 7' },
    }
    const cfg = configs[type] || configs.sale
    return (
      <div style={{ width: 36, height: 36, borderRadius: 10, background: cfg.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={cfg.color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d={cfg.icon} />
        </svg>
      </div>
    )
  }

  return (
    <SellerLayout title="Carteira">
      {/* Withdraw bottom sheet */}
      {showWithdraw && (
        <div
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', zIndex: 100, display: 'flex', alignItems: 'flex-end' }}
          onClick={e => { if (e.target === e.currentTarget) resetWithdraw() }}
        >
          <div style={{ background: '#141414', borderRadius: '20px 20px 0 0', border: '1px solid #2A2A2A', padding: '20px 20px 40px', width: '100%', maxWidth: 430, margin: '0 auto' }}>
            <div style={{ width: 36, height: 4, borderRadius: 2, background: '#2A2A2A', margin: '0 auto 20px' }} />

            {withdrawStep === 1 && <>
              <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF', marginBottom: 4 }}>Levantar fundos</h3>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A', marginBottom: 20 }}>
                Disponível: <span style={{ color: '#C9A84C', fontWeight: 600 }}>{formatPrice(available)}</span>
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Valor (Kz)</label>
                  <input className="input-base" type="number" inputMode="numeric" placeholder="Mínimo 1 000 Kz"
                    value={withdrawAmount} onChange={e => { setWithdrawAmount(e.target.value); setAmountError('') }}
                    style={{ borderColor: amountError ? 'rgba(220,38,38,0.5)' : undefined }} />
                  {amountError && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#F87171' }}>{amountError}</p>}
                  {/* Quick amount buttons */}
                  <div style={{ display: 'flex', gap: 8 }}>
                    {[5000, 10000, 20000, available].map(amt => (
                      <button key={amt} onClick={() => { setWithdrawAmount(String(amt)); setAmountError('') }}
                        style={{ flex: 1, padding: '6px 0', borderRadius: 8, border: '1px solid #2A2A2A', background: withdrawAmount === String(amt) ? 'rgba(201,168,76,0.1)' : 'transparent', fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: withdrawAmount === String(amt) ? '#C9A84C' : '#9A9A9A', cursor: 'pointer' }}>
                        {amt === available ? 'Tudo' : `${(amt / 1000).toFixed(0)}K`}
                      </button>
                    ))}
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <label style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#9A9A9A', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Nº Multicaixa Express</label>
                  <div style={{ display: 'flex' }}>
                    <div style={{ display: 'flex', alignItems: 'center', padding: '0 14px', background: '#1E1E1E', border: '1px solid #2A2A2A', borderRight: 'none', borderRadius: '12px 0 0 12px', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#C9A84C', fontWeight: 600, whiteSpace: 'nowrap' }}>🇦🇴 +244</div>
                    <input className="input-base" type="tel" inputMode="numeric" placeholder="9xx xxx xxx"
                      value={phone} onChange={e => { setPhone(e.target.value); setPhoneError('') }}
                      style={{ borderRadius: '0 12px 12px 0', flex: 1, borderColor: phoneError ? 'rgba(220,38,38,0.5)' : undefined }} />
                  </div>
                  {phoneError && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#F87171' }}>{phoneError}</p>}
                </div>

                <div style={{ background: 'rgba(201,168,76,0.06)', border: '1px solid rgba(201,168,76,0.15)', borderRadius: 10, padding: '10px 14px' }}>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#C9A84C', lineHeight: 1.5 }}>
                    ⚡ Processado em 1-2 dias úteis via Multicaixa Express. Taxa de levantamento: grátis.
                  </p>
                </div>

                <button className="btn-primary" onClick={() => { if (validateWithdraw()) setWithdrawStep(2) }}>
                  Continuar
                </button>
                <button onClick={resetWithdraw} className="btn-secondary">Cancelar</button>
              </div>
            </>}

            {withdrawStep === 2 && <>
              <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700, color: '#FFFFFF', marginBottom: 20 }}>Confirmar levantamento</h3>
              <div style={{ background: '#0F0F0F', borderRadius: 14, padding: 16, marginBottom: 20, display: 'flex', flexDirection: 'column', gap: 10 }}>
                {[
                  { l: 'Valor', v: formatPrice(Number(withdrawAmount)) },
                  { l: 'Para', v: `+244 ${phone}` },
                  { l: 'Via', v: 'Multicaixa Express' },
                  { l: 'Taxa', v: 'Grátis' },
                  { l: 'Prazo', v: '1-2 dias úteis' },
                ].map(row => (
                  <div key={row.l} style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>{row.l}</span>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', fontWeight: 500 }}>{row.v}</span>
                  </div>
                ))}
                <div style={{ height: 1, background: '#2A2A2A' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 700, color: '#FFFFFF' }}>Total a receber</span>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 700, color: '#C9A84C' }}>{formatPrice(Number(withdrawAmount))}</span>
                </div>
              </div>
              <button className="btn-primary" onClick={handleWithdraw} disabled={loading} style={{ opacity: loading ? 0.7 : 1, marginBottom: 10 }}>
                {loading ? 'A processar...' : 'Confirmar levantamento'}
              </button>
              <button onClick={() => setWithdrawStep(1)} className="btn-secondary">Voltar</button>
            </>}

            {withdrawStep === 3 && (
              <div style={{ textAlign: 'center', padding: '10px 0' }}>
                <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'rgba(5,150,105,0.1)', border: '2px solid rgba(5,150,105,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px' }}>
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                </div>
                <h3 style={{ fontFamily: "'Playfair Display', serif", fontSize: 22, fontWeight: 700, color: '#FFFFFF', marginBottom: 8 }}>Pedido enviado!</h3>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: '#9A9A9A', lineHeight: 1.6, marginBottom: 24 }}>
                  O seu pedido de levantamento de <span style={{ color: '#C9A84C' }}>{formatPrice(Number(withdrawAmount))}</span> foi enviado. Será processado em 1-2 dias úteis.
                </p>
                <button className="btn-primary" onClick={resetWithdraw}>Fechar</button>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="screen" style={{ flex: 1 }}>
        <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Balance card */}
          <div style={{ borderRadius: 20, padding: 24, background: 'linear-gradient(135deg, #C9A84C 0%, #A67C35 100%)', position: 'relative', overflow: 'hidden' }}>
            <div style={{ position: 'absolute', top: -30, right: -30, width: 120, height: 120, borderRadius: '50%', background: 'rgba(255,255,255,0.08)' }} />
            <div style={{ position: 'absolute', bottom: -20, right: 40, width: 80, height: 80, borderRadius: '50%', background: 'rgba(255,255,255,0.05)' }} />

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(0,0,0,0.6)', fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase' }}>
                Saldo disponível
              </p>
              <button onClick={() => setShowBalance(v => !v)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', opacity: 0.6 }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#0A0A0A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  {showBalance
                    ? <><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></>
                    : <><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" /><line x1="1" y1="1" x2="23" y2="23" /></>
                  }
                </svg>
              </button>
            </div>

            <p style={{ fontFamily: "'Playfair Display', serif", fontSize: 34, fontWeight: 700, color: '#0A0A0A', marginBottom: 4 }}>
              {showBalance ? formatPrice(available) : '••••••• Kz'}
            </p>

            {pending > 0 && (
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(0,0,0,0.55)', marginBottom: 20 }}>
                + {showBalance ? formatPrice(pending) : '••••• Kz'} pendente
              </p>
            )}

            <div style={{ display: 'flex', gap: 10 }}>
              <button onClick={() => setShowWithdraw(true)}
                style={{ flex: 1, padding: '11px 0', borderRadius: 12, background: '#0A0A0A', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#C9A84C' }}>
                Levantar
              </button>
              <button style={{ flex: 1, padding: '11px 0', borderRadius: 12, background: 'rgba(0,0,0,0.12)', border: '1px solid rgba(0,0,0,0.12)', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 500, color: '#0A0A0A' }}>
                Partilhar IBAN
              </button>
            </div>
          </div>

          {/* Stats */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
            {[
              { label: 'Total ganho', value: formatPrice(totalEarned), color: '#C9A84C' },
              { label: 'Levantado', value: formatPrice(totalWithdrawn), color: '#3b82f6' },
              { label: 'Comissões', value: formatPrice(totalCommissions), color: '#9A9A9A' },
            ].map(stat => (
              <div key={stat.label} style={{ background: '#141414', borderRadius: 12, border: '1px solid #1E1E1E', padding: '12px 10px', textAlign: 'center' }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: stat.color, marginBottom: 2 }}>
                  {showBalance ? stat.value : '•••'}
                </p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#9A9A9A' }}>{stat.label}</p>
              </div>
            ))}
          </div>

          {/* Commission info */}
          <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', padding: 16 }}>
            <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: '#FFFFFF', marginBottom: 12 }}>
              Como funciona a comissão?
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>Taxa MICHA Express</span>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', fontWeight: 500 }}>5% por venda</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>Taxa de levantamento</span>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#059669', fontWeight: 500 }}>Grátis</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>Mínimo de levantamento</span>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', fontWeight: 500 }}>1 000 Kz</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#9A9A9A' }}>Prazo de pagamento</span>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', fontWeight: 500 }}>1-2 dias úteis</span>
              </div>
            </div>
          </div>

          {/* Transactions */}
          <div>
            <h3 style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, fontWeight: 600, color: '#9A9A9A', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 12 }}>
              Histórico de transações
            </h3>
            <div style={{ background: '#141414', borderRadius: 14, border: '1px solid #1E1E1E', overflow: 'hidden' }}>
              {TRANSACTIONS.map((tx, i) => {
                const netAmount = tx.amount + (tx.fee || 0)
                const isPositive = netAmount > 0
                return (
                  <div key={tx.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px', borderBottom: i < TRANSACTIONS.length - 1 ? '1px solid #1E1E1E' : 'none' }}>
                    <TypeIcon type={tx.type} amount={tx.amount} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#FFFFFF', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{tx.label}</p>
                      <div style={{ display: 'flex', gap: 8, marginTop: 2 }}>
                        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#9A9A9A' }}>{tx.date}</p>
                        {tx.fee < 0 && <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#555' }}>Comissão: {formatPrice(Math.abs(tx.fee))}</p>}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right', flexShrink: 0 }}>
                      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 700, color: isPositive ? '#059669' : '#dc2626' }}>
                        {showBalance ? `${isPositive ? '+' : ''}${formatPrice(Math.abs(netAmount))}` : '•••'}
                      </p>
                      {tx.status === 'pending' && (
                        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: '#f59e0b', marginTop: 2 }}>Pendente</p>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

        </div>
      </div>
    </SellerLayout>
  )
}
