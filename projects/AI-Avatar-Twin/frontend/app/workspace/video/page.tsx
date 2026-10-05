'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Clapperboard, UserRound } from 'lucide-react';
import { listProfiles, listScripts, listVideos, createVideo, getVideo, Profile, Script } from '@/lib/api/client';
import { useToast } from '@/components/toast';
import { BackStep } from '@/components/back-step';
import { getProjectFromUrl, getRememberedProject, projectHref } from '@/lib/project-url';
import { readWorkspaceDraft, saveWorkspaceDraft } from '@/lib/workspace-draft';

type VideoDraft = { selectedScriptId?: string; selectedProfiles?: Record<string, string> };

export default function VideoPage() {
  const [scripts, setScripts] = useState<Script[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [selectedProfiles, setSelectedProfiles] = useState<Record<string, string>>({});
  const [selectedScriptId, setSelectedScriptId] = useState('');
  const [statuses, setStatuses] = useState<Record<string, string>>({});
  const [startedAt, setStartedAt] = useState<Record<string, number>>({});
  const [now, setNow] = useState(() => Date.now());
  const [err, setErr] = useState('');
  const [projectId, setProjectId] = useState('');
  const [loading, setLoading] = useState(true);
  const activeRef = useRef(false);
  const submittingRef = useRef(new Set<string>());
  const latestRef = useRef<Record<string, string>>({});
  const timersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const { show } = useToast();

  async function poll(videoId: string, scriptId: string) {
    if (!activeRef.current || latestRef.current[scriptId] !== videoId) return;
    try {
      const v = await getVideo(videoId);
      if (!activeRef.current || latestRef.current[scriptId] !== videoId) return;
      setStatuses((s) => ({ ...s, [scriptId]: v.status }));
      setNow(Date.now());
      if (v.status === 'success') {
        show('success', '视频已生成，去「我的视频」查看');
        return;
      }
      if (v.status === 'failed') {
        show('error', '视频生成失败，可重试');
        return;
      }
      timersRef.current[scriptId] = setTimeout(() => poll(videoId, scriptId), 3000);
    } catch (e) {
      if (!activeRef.current || latestRef.current[scriptId] !== videoId) return;
      setErr(e instanceof Error ? e.message : '查询失败');
      timersRef.current[scriptId] = setTimeout(() => poll(videoId, scriptId), 5000);
    }
  }

  useEffect(() => {
    activeRef.current = true;
    let cancelled = false;
    (async () => {
      const currentProjectId = getProjectFromUrl() || getRememberedProject();
      setProjectId(currentProjectId);
      const [scriptList, videoList, profileList] = await Promise.all([
        currentProjectId ? listScripts(currentProjectId) : Promise.resolve([]),
        listVideos(),
        currentProjectId ? listProfiles(currentProjectId) : Promise.resolve([]),
      ]);
      if (cancelled) return;
      const target = new URLSearchParams(window.location.search).get('script') || '';
      const saved = readWorkspaceDraft<VideoDraft>('video', currentProjectId);
      const initialScriptId = scriptList.some((script) => script.id === target)
        ? target
        : scriptList.some((script) => script.id === saved?.selectedScriptId)
          ? saved?.selectedScriptId || ''
          : '';
      setSelectedScriptId(initialScriptId);
      setScripts(scriptList);
      setProfiles(profileList);
      const availableProfileIds = new Set(profileList.map((profile) => profile.id));
      setSelectedProfiles(Object.fromEntries(scriptList.map((s) => {
        const savedProfileId = saved?.selectedProfiles?.[s.id] || '';
        return [s.id, availableProfileIds.has(savedProfileId) ? savedProfileId : ''];
      })));
      const nextStatuses: Record<string, string> = {};
      const nextStarted: Record<string, number> = {};
      // The API returns newest first. Only the newest task may update each script.
      const scriptIds = new Set(scriptList.map((script) => script.id));
      for (const v of videoList) {
        if (!scriptIds.has(v.script_id) || nextStatuses[v.script_id]) continue;
        nextStatuses[v.script_id] = v.status;
        latestRef.current[v.script_id] = v.id;
        if (v.status === 'queued' || v.status === 'rendering') poll(v.id, v.script_id);
      }
      setStatuses(nextStatuses);
      setStartedAt(nextStarted);
      setLoading(false);
    })().catch((e) => { if (!cancelled) { setErr(e.message); setLoading(false); } });
    const timers = timersRef.current;
    return () => {
      cancelled = true;
      activeRef.current = false;
      latestRef.current = {};
      Object.values(timers).forEach(clearTimeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (loading || !projectId || scripts.length === 0) return;
    saveWorkspaceDraft<VideoDraft>('video', projectId, { selectedScriptId, selectedProfiles });
  }, [loading, projectId, scripts.length, selectedProfiles, selectedScriptId]);

  const handleGenerate = async (scriptId: string) => {
    if (loading || submittingRef.current.has(scriptId) || (statuses[scriptId] && statuses[scriptId] !== 'failed')) return;
    setErr('');
    const profileId = selectedProfiles[scriptId];
    if (!profileId || !profiles.some((profile) => profile.id === profileId)) {
      setErr('请先选择一个数字人形象，再生成视频。');
      return;
    }
    submittingRef.current.add(scriptId);
    setStatuses((s) => ({ ...s, [scriptId]: 'submitting' }));
    try {
      const v = await createVideo(scriptId, profileId);
      if (!activeRef.current) return;
      latestRef.current[scriptId] = v.id;
      if (timersRef.current[scriptId]) clearTimeout(timersRef.current[scriptId]);
      setStatuses((s) => ({ ...s, [scriptId]: v.status }));
      setStartedAt((s) => ({ ...s, [scriptId]: Date.now() }));
      setNow(Date.now());
      show('success', '视频任务已创建，预计 5-10 分钟，可先离开，完成后会提示');
      poll(v.id, scriptId);
    } catch (e) {
      if (!activeRef.current) return;
      setErr(e instanceof Error ? e.message : '生成失败');
      // Reconcile an ambiguous POST failure before allowing another paid submission.
      try {
        const videos = await listVideos();
        if (!activeRef.current) return;
        const latest = videos.find((video) => video.script_id === scriptId);
        if (latest) {
          latestRef.current[scriptId] = latest.id;
          setStatuses((s) => ({ ...s, [scriptId]: latest.status }));
          if (latest.status === 'queued' || latest.status === 'rendering') poll(latest.id, scriptId);
        } else setStatuses((s) => ({ ...s, [scriptId]: 'failed' }));
      } catch {
        if (activeRef.current) setErr('提交结果暂时无法确认，请刷新查询任务状态后再试。');
      }
    } finally {
      submittingRef.current.delete(scriptId);
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="title">选择脚本和出镜形象</h1>
        </div>
        <BackStep fallbackHref={projectHref('/workspace/content', projectId)} />
      </div>
      {err && <div className="err" style={{ marginBottom: 12 }}>{err}</div>}

      {loading && <div className="muted">正在加载脚本和视频任务…</div>}
      {!loading && scripts.length === 0 && <div className="empty-block"><p>还没有可用脚本</p><Link className="btn btn-primary" href={projectHref('/workspace/content', projectId)}>去生成脚本</Link></div>}
      {scripts.length > 0 && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="row" style={{ justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontWeight: 720 }}>1. 选择本次使用的脚本</div>
              <div className="muted">从工作台进入时会自动选中刚确认的脚本，也可以在这里更换。</div>
            </div>
            <select
              className="input"
              style={{ width: 360, maxWidth: '100%' }}
              aria-label="选择本次使用的脚本"
              value={selectedScriptId}
              onChange={(event) => setSelectedScriptId(event.target.value)}
            >
              <option value="">请选择脚本</option>
              {scripts.map((script) => (
                <option key={script.id} value={script.id}>{script.content.slice(0, 34)}</option>
              ))}
            </select>
          </div>
        </div>
      )}
      {scripts.length > 0 && profiles.length === 0 && (
        <div className="card" style={{ marginBottom: 12, borderColor: 'var(--border)', background: 'var(--surface)' }}>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontWeight: 720 }}>还没有可用形象</div>
              <div className="muted">先创建一个数字人角色，上传照片或选择模板后再生成视频。</div>
            </div>
            <Link className="btn" href={projectHref('/workspace/profile', projectId)}>
              去创建形象
            </Link>
          </div>
        </div>
      )}

      {scripts.filter((script) => script.id === selectedScriptId).map((s) => {
        const isTargetScript = selectedScriptId === s.id;
        const status = statuses[s.id];
        const isGenerating = status && status !== 'success' && status !== 'failed';
        const minutes = startedAt[s.id] ? Math.floor((now - startedAt[s.id]) / 60000) : 0;
        const selectedProfileId = selectedProfiles[s.id] || '';
        return (
          <div key={s.id} className="card" style={{
            marginBottom: 10,
            borderColor: isTargetScript ? 'var(--primary)' : 'var(--border)',
            background: 'var(--surface)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <Clapperboard size={18} style={{ color: 'var(--primary)' }} />
              <span className="muted">脚本 {s.id.slice(-6)}（{s.duration_target} 秒）</span>
              {isTargetScript && <span className="tag" style={{ color: 'var(--primary)' }}>当前脚本</span>}
              {status === 'success' && <span className="tag" style={{ color: 'var(--success)' }}>已有视频</span>}
              {status === 'failed' && <span className="tag" style={{ color: 'var(--danger)' }}>上次失败</span>}
              {isGenerating && (
                <span className="tag status-progress" role="status">
                  <span className="spin" aria-hidden="true" /> {status === 'submitting' ? '正在提交任务' : status === 'queued' ? '排队中' : '视频生成中'}{startedAt[s.id] ? `，已 ${minutes} 分钟` : ''}
                </span>
              )}
            </div>
            <div className="muted" style={{ marginTop: 6, maxHeight: 80, overflow: 'hidden' }}>
              {(s.content || '').slice(0, 200)}
            </div>
            <details style={{ marginTop: 10 }}><summary>查看完整脚本</summary><p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{s.content}</p></details>
            {s.risk_flags.length > 0 && (
              <div className="err" style={{ marginTop: 10 }} role="note">
                <strong>生成前请核对以下脚本风险</strong>
                <ul>{s.risk_flags.map((risk, index) => <li key={`${index}-${risk}`}>{risk}</li>)}</ul>
                <p>请核对完整脚本及风险提示，确认内容可用后再点击生成视频。</p>
              </div>
            )}
            <div style={{ marginTop: 10, paddingBlock: 10 }}>
              <div className="row" style={{ justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                <div className="row" style={{ flex: '1 1 260px' }}>
                  <UserRound size={16} style={{ color: 'var(--primary)' }} />
                  <div>
                    <div style={{ fontWeight: 700 }}>2. 选择出镜形象</div>
                    <div className="muted">必须先选择，选中的数字人会出现在成片里。</div>
                  </div>
                </div>
                {profiles.length > 0 ? (
                  <select
                    className="input"
                    style={{ width: 240, maxWidth: '100%' }}
                    aria-label="选择出镜形象"
                    value={selectedProfileId}
                    onChange={(e) => setSelectedProfiles((prev) => ({ ...prev, [s.id]: e.target.value }))}
                    disabled={Boolean(isGenerating)}
                  >
                    <option value="">请选择出镜形象</option>
                    {profiles.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}{p.avatar_type === 'uploaded_self' ? ' · 已上传照片' : ` · 模板 ${p.template_id || 1}`}
                      </option>
                    ))}
                  </select>
                ) : (
                  <Link className="btn btn-ghost" href={projectHref('/workspace/profile', projectId)}>先创建形象</Link>
                )}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
              {!status && (
                <button className="btn btn-primary" onClick={() => handleGenerate(s.id)} disabled={profiles.length === 0 || !selectedProfileId}>
                  <Clapperboard size={16} /> 3. 确认生成视频
                </button>
              )}
              {status === 'success' && <Link href={projectHref('/workspace/videos', projectId)} className="btn btn-ghost">去「我的视频」查看</Link>}
              {status === 'failed' && <button className="btn" disabled={!selectedProfileId || loading} onClick={() => handleGenerate(s.id)}>重试</button>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
