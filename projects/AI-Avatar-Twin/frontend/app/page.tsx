'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowRight } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { requestCode, verifyCode, setToken, getToken } from '@/lib/api/client';
import BrandMark from '@/components/brand-mark';

export default function LoginPage() {
  const router = useRouter();
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [hint, setHint] = useState('');
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [invalidField, setInvalidField] = useState<'phone' | 'code' | null>(null);
  const phoneRef = useRef<HTMLInputElement>(null);
  const codeRef = useRef<HTMLInputElement>(null);
  const pendingRef = useRef(false);
  const retryAtRef = useRef(0);

  useEffect(() => {
    if (getToken()) router.replace('/workspace');
  }, [router]);

  useEffect(() => {
    if (!cooldown) return;
    const timer = window.setInterval(() => {
      setCooldown(Math.max(0, Math.ceil((retryAtRef.current - Date.now()) / 1000)));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [cooldown]);

  const validatePhone = () => {
    if (/^[0-9]{6,20}$/.test(phone.trim())) return true;
    setErr('请输入有效手机号（6–20 位数字）');
    setInvalidField('phone');
    phoneRef.current?.focus();
    return false;
  };

  const handleCode = async () => {
    if (pendingRef.current || Date.now() < retryAtRef.current) return;
    setErr('');
    setInvalidField(null);
    if (!validatePhone()) return;
    pendingRef.current = true;
    setSending(true);
    setHint('');
    try {
      const r = await requestCode(phone.trim());
      setHint(r.dev_code ? `测试验证码：${r.dev_code}` : '验证码已发送');
      retryAtRef.current = Date.now() + 60_000;
      setCooldown(60);
      codeRef.current?.focus();
    } catch (e) {
      setErr(e instanceof Error ? e.message : '获取验证码失败');
    } finally {
      pendingRef.current = false;
      setSending(false);
    }
  };

  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pendingRef.current) return;
    setErr('');
    setInvalidField(null);
    if (!validatePhone()) return;
    if (!/^[0-9]{4,10}$/.test(code.trim())) {
      setErr('请输入有效验证码（4–10 位数字）');
      setInvalidField('code');
      codeRef.current?.focus();
      return;
    }
    pendingRef.current = true;
    setLoading(true);
    try {
      const r = await verifyCode(phone.trim(), code.trim());
      setToken(r.token);
      router.push('/workspace');
    } catch (e) {
      setErr(e instanceof Error ? e.message : '登录失败');
      pendingRef.current = false;
      setLoading(false);
    }
  };

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="auth-title">
        <div className="auth-brand">
          <BrandMark />
          <span>Avatar Twin</span>
        </div>
        <div className="auth-portraits" aria-hidden="true">
          {['photo-1534528741775-53994a69daeb', 'photo-1506794778202-cad84cf45f1d', 'photo-1524504388940-b1c1722653e1'].map((id) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={id} src={`https://images.unsplash.com/${id}?auto=format&fit=crop&w=180&h=220&q=85`} alt="" width={64} height={76} />
          ))}
        </div>
        <h1 id="auth-title" className="auth-heading">登录创作空间</h1>

        <form className="auth-form" onSubmit={handleLogin} noValidate aria-busy={loading || sending}>
          <label className="label" htmlFor="phone">手机号</label>
          <input
            ref={phoneRef} id="phone" name="phone" className="input" type="tel"
            inputMode="tel" autoComplete="tel" placeholder="输入手机号"
            required maxLength={20} value={phone} disabled={sending || loading}
            aria-invalid={invalidField === 'phone'}
            aria-describedby={invalidField === 'phone' ? 'auth-error' : undefined}
            onChange={(e) => {
              setPhone(e.target.value);
              setCode('');
              setHint('');
              setErr('');
              setInvalidField(null);
            }}
          />
          <label className="label" htmlFor="code">验证码</label>
          <div className="auth-code-row">
            <input
              ref={codeRef} id="code" name="code" className="input" type="text"
              inputMode="numeric" autoComplete="one-time-code" placeholder="输入验证码"
              required maxLength={10} value={code} disabled={loading}
              aria-invalid={invalidField === 'code'}
              aria-describedby={invalidField === 'code' ? 'auth-error' : 'auth-hint'}
              onChange={(e) => { setCode(e.target.value); setErr(''); setInvalidField(null); }}
            />
            <button type="button" className="btn btn-ghost" onClick={handleCode} disabled={sending || loading || cooldown > 0}>
              {sending ? '发送中…' : cooldown > 0 ? `${cooldown} 秒后重发` : '获取验证码'}
            </button>
          </div>
          <p id="auth-hint" className="auth-note" role="status">{hint}</p>
          {err && <p id="auth-error" className="err" role="alert">{err}</p>}
          <button type="submit" className="btn auth-submit" disabled={loading || sending}>
            {loading ? '登录中…' : '登录'}
            {loading ? <span className="spin" aria-hidden="true" /> : <ArrowRight size={18} aria-hidden="true" />}
          </button>
        </form>
      </section>
    </main>
  );
}
