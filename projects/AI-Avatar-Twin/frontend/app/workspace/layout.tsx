'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { LayoutDashboard, UserRound, FileText, Clapperboard, Film, LogOut } from 'lucide-react';
import { getToken, logout, clearToken } from '@/lib/api/client';
import { ToastProvider } from '@/components/toast';
import { getProjectFromUrl, getRememberedProject, projectHref, PROJECT_CHANGE_EVENT } from '@/lib/project-url';
import BrandMark from '@/components/brand-mark';

const NAV = [
  { href: '/workspace', label: '工作台', icon: LayoutDashboard },
  { href: '/workspace/profile', label: '我的角色', icon: UserRound },
  { href: '/workspace/content', label: '选题与脚本', icon: FileText },
  { href: '/workspace/video', label: '形象与视频', icon: Clapperboard },
  { href: '/workspace/videos', label: '我的视频', icon: Film },
];

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [projectId, setProjectId] = useState('');

  useEffect(() => {
    if (!getToken()) router.replace('/');
  }, [router]);

  useEffect(() => {
    const syncProject = (event?: Event) => {
      const customProject = event instanceof CustomEvent ? String(event.detail || '') : '';
      setProjectId(customProject || getProjectFromUrl() || getRememberedProject());
    };
    syncProject();
    window.addEventListener(PROJECT_CHANGE_EVENT, syncProject);
    window.addEventListener('popstate', syncProject);
    return () => {
      window.removeEventListener(PROJECT_CHANGE_EVENT, syncProject);
      window.removeEventListener('popstate', syncProject);
    };
  }, []);

  const handleLogout = async () => {
    try {
      await logout();
    } catch {
      /* 忽略登出失败 */
    }
    clearToken();
    router.replace('/');
  };

  return (
    <div className="shell">
      <aside className="sidebar hide-mobile">
        <div className="brand">
          <div className="brand-lockup">
            <BrandMark size={38} />
            <div className="brand-copy">
              <div className="brand-title">Avatar Twin</div>
              <div className="brand-subtitle">AI 短视频创作台</div>
            </div>
          </div>
        </div>
        <nav className="sidebar-nav" aria-label="工作台导航">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={projectHref(href, projectId)}
              className={`nav-link ${pathname === href ? 'active' : ''}`}
              aria-current={pathname === href ? 'page' : undefined}
            >
              <Icon size={18} />
              {label}
            </Link>
          ))}
        </nav>
      </aside>

      <main className="workspace-main">
        <div className="workspace-utility">
          <button className="btn btn-ghost logout-top" onClick={handleLogout}>
            <LogOut size={16} /> 退出登录
          </button>
        </div>
        <ToastProvider>{children}</ToastProvider>
      </main>

      <nav className="show-mobile bottom-nav">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={projectHref(href, projectId)} className={`bottom-nav-link ${pathname === href ? 'active' : ''}`}>
            <Icon size={20} />
            {label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
