'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, Clapperboard, FileText, Film, Play, Plus, Trash2, UserRound } from 'lucide-react';
import { AgentEvent, createProject, deleteProfile, listProjects, listProfiles, listScripts, listVideos, me, Profile, Script, streamAgent, User } from '@/lib/api/client';
import { getProjectFromUrl, getRememberedProject, projectHref, rememberProject } from '@/lib/project-url';
import { readWorkspaceDraft, saveWorkspaceDraft } from '@/lib/workspace-draft';
import { ConfirmDialog } from '@/components/confirm-dialog';

type HomeDraft = {
  goal?: string;
  profileId?: string;
};

export default function WorkspaceHome() {
  const [user, setUser] = useState<User | null>(null);
  const [projectCount, setProjectCount] = useState(0);
  const [profileCount, setProfileCount] = useState(0);
  const [videoCount, setVideoCount] = useState(0);
  const [projectId, setProjectId] = useState('');
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [scripts, setScripts] = useState<Script[]>([]);
  const [profileId, setProfileId] = useState('');
  const [goal, setGoal] = useState('');
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([]);
  const [agentRunning, setAgentRunning] = useState(false);
  const [agentScript, setAgentScript] = useState('');
  const [agentScriptId, setAgentScriptId] = useState('');
  const [err, setErr] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<Profile | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const operationRef = useRef(false);

  useEffect(() => {
    (async () => {
      try {
        setUser(await me());
        let projects = await listProjects();
        if (projects.length === 0) {
          const created = await createProject('我的第一个项目');
          projects = [created];
        }
        setProjectCount(projects.length);
        if (projects.length) {
          const target = getProjectFromUrl() || getRememberedProject();
          const picked = projects.find((p) => p.id === target) || projects[0];
          rememberProject(picked.id);
          const [profileList, scriptList] = await Promise.all([listProfiles(picked.id), listScripts(picked.id)]);
          const saved = readWorkspaceDraft<HomeDraft>('home', picked.id);
          setProfiles(profileList);
          setScripts(scriptList);
          setGoal(saved?.goal ?? '');
          setProfileId(profileList.some((p) => p.id === saved?.profileId) ? saved?.profileId || '' : profileList[0]?.id || '');
          setProfileCount(profileList.length);
          setProjectId(picked.id);
        }
        setVideoCount((await listVideos()).length);
      } catch (e) {
        setErr(e instanceof Error ? e.message : '加载失败');
      }
    })();
  }, []);

  useEffect(() => {
    if (!projectId) return;
    saveWorkspaceDraft<HomeDraft>('home', projectId, {
      goal,
      profileId,
    });
  }, [goal, profileId, projectId]);

  const handleRunAgent = async () => {
    if (!goal.trim() || !projectId || !profileId || operationRef.current) return;
    operationRef.current = true;
    setErr('');
    setAgentEvents([{ type: 'local_start', status: 'starting', thought: '已收到目标，正在连接创作流程。通常需要几秒钟开始返回进度。' }]);
    setAgentScript('');
    setAgentScriptId('');
    setAgentRunning(true);
    try {
      for await (const ev of streamAgent(goal.trim(), profileId, projectId)) {
        setAgentEvents((items) => [...items, ev]);
        if (ev.type === 'done' && ev.script?.content) {
          setAgentScript(ev.script.content);
          setAgentScriptId(ev.script.id || '');
          if (ev.script.id) {
            const nextScripts = await listScripts(projectId);
            setScripts(nextScripts);
          }
        }
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : '自动生成失败');
    } finally {
      operationRef.current = false;
      setAgentRunning(false);
    }
  };

  const handleDeleteCurrentProfile = async () => {
    const currentProfile = deleteTarget;
    if (!currentProfile || operationRef.current) return;
    operationRef.current = true;
    setDeleting(true);
    setDeleteError('');
    try {
      await deleteProfile(currentProfile.id);
      const nextProfiles = await listProfiles(projectId);
      setProfiles(nextProfiles);
      setProfileCount(nextProfiles.length);
      setProfileId(nextProfiles[0]?.id || '');
      setDeleteTarget(null);
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : '删除角色失败');
    } finally {
      operationRef.current = false;
      setDeleting(false);
    }
  };

  const latestDone = agentEvents.findLast((ev) => ev.type === 'done');
  const videoHref = buildScriptVideoHref(projectId, agentScriptId);
  const progress = getAgentProgress(agentEvents, agentRunning, Boolean(agentScript));
  const isReady = Boolean(user && projectId);
  const hasProfiles = profiles.length > 0;

  return (
    <div className="studio-home">
      <div className="page-head studio-hero">
        <div>
          <h1 className="title">今天，想创作什么？</h1>
        </div>
      </div>

      {err && <div className="err" style={{ marginBottom: 16 }}>{err}</div>}

      <nav className="creation-modes" aria-label="创作方式">
        <span aria-current="page"><Play size={15} /> 目标创作</span>
        <Link href={projectHref('/workspace/content', projectId)}><FileText size={15} /> 链接选题</Link>
      </nav>

      <div className="card command-card">
        <div style={{ display: 'grid', gap: 10 }}>
          <textarea
            className="input command-input"
            style={{ resize: 'vertical' }}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            aria-label="创作目标"
            placeholder="输入本次主题或文章链接…"
          />
          <div className="command-footer">
            {hasProfiles ? (
              <div className="command-meta">
                <div className="row">
                  <select className="input" aria-label="脚本风格参考角色" style={{ width: 160 }} value={profileId} disabled={agentRunning || deleting} onChange={(e) => setProfileId(e.target.value)}>
                    {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                  <Link className="btn btn-ghost" href={projectHref('/workspace/profile', projectId)}>
                    <Plus size={16} /> 新建角色
                  </Link>
                  <button className="btn btn-ghost danger-btn" onClick={() => { setDeleteError(''); setDeleteTarget(profiles.find((p) => p.id === profileId) || null); }} disabled={!profileId || agentRunning || deleting} title="删除当前选中的角色" aria-label="删除当前选中的角色">
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ) : <div />}
            {hasProfiles ? (
              <button className="btn btn-primary" onClick={handleRunAgent} disabled={!isReady || agentRunning || !goal.trim() || !profileId}>
                {agentRunning ? <span className="spin" /> : <Play size={16} />}
                {agentRunning ? '正在生成脚本' : '开始生成脚本'}
              </button>
            ) : (
              <Link className={`btn btn-primary ${!projectId ? 'disabled-link' : ''}`} href={projectHref('/workspace/profile', projectId)}>
                <Plus size={16} /> 创建角色
              </Link>
            )}
          </div>
        </div>

        {agentEvents.length > 0 && (
          <div className="card progress-card">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <div style={{ fontWeight: 720 }}>{progress.title}</div>
              {progress.done && <CheckCircle2 size={16} style={{ color: 'var(--success)' }} />}
            </div>
            <div className="muted" style={{ marginTop: 4 }}>{progress.detail}</div>
            <div className="row" style={{ marginTop: 10, gap: 6 }}>
              {progress.stages.map((stage, idx) => (
                <span
                  key={stage}
                  className="tag"
                  style={idx <= progress.activeIndex ? { color: 'var(--text)', borderColor: 'var(--text)' } : {}}
                >
                  {stage}
                </span>
              ))}
            </div>
          </div>
        )}

        {agentScript && (
          <div className="card script-result">
            <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
              <div>
                <div style={{ fontWeight: 720 }}>已选择的脚本</div>
                <div className="muted">下一步只会使用这一个脚本，不会自动生成视频。</div>
              </div>
              {scripts.length > 0 && (
                <select
                  className="input"
                  style={{ width: 320 }}
                  aria-label="选择用于下一步的脚本"
                  value={agentScriptId}
                  onChange={(event) => {
                    const selected = scripts.find((script) => script.id === event.target.value);
                    if (!selected) return;
                    setAgentScriptId(selected.id);
                    setAgentScript(selected.content);
                  }}
                >
                  {scripts.map((script) => (
                    <option key={script.id} value={script.id}>
                      {script.id === agentScriptId ? '当前 · ' : ''}{script.content.slice(0, 28)}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div className="script-preview-line">{agentScript}</div>
            <div className="row" style={{ marginTop: 10 }}>
              <Link className="btn btn-ghost" href={buildScriptContentHref(projectId, agentScriptId)}>编辑当前脚本</Link>
              <Link className="btn" href={videoHref}>下一步：选择出镜形象</Link>
            </div>
          </div>
        )}

        {latestDone?.status === 'incomplete' && (
          <div className="err" style={{ marginTop: 12 }}>自动生成已停止但未产出脚本，请补充目标里的信息源链接或切到手动流程。</div>
        )}
      </div>

      <div className="grid-auto studio-shortcuts">
        {[
          { href: '/workspace/profile', label: '我的角色', desc: `${projectCount} 个项目 · ${profileCount} 个角色`, icon: UserRound },
          { href: '/workspace/content', label: '选题与脚本', desc: '从链接到脚本', icon: FileText },
          { href: '/workspace/video', label: '形象与视频', desc: '选脚本、选形象、再生成', icon: Clapperboard },
          { href: '/workspace/videos', label: '我的视频', desc: `${videoCount} 条视频`, icon: Film },
        ].map(({ href, label, desc, icon: Icon }) => (
          <Link key={href} href={projectHref(href, projectId)} className="card module-card" style={{ display: 'block' }}>
            <span className="module-icon"><Icon size={18} /></span>
            <div style={{ fontWeight: 600, marginTop: 8 }}>{label}</div>
            <div className="muted">{desc}</div>
          </Link>
        ))}
      </div>
      <ConfirmDialog open={Boolean(deleteTarget)} title={`删除角色「${deleteTarget?.name || ''}」？`}
        description="删除后无法恢复，也不能再用这个角色生成视频。" busy={deleting} error={deleteError}
        onCancel={() => setDeleteTarget(null)} onConfirm={handleDeleteCurrentProfile} />
    </div>
  );
}

function getAgentProgress(events: AgentEvent[], running: boolean, hasScript: boolean) {
  const stages = ['准备资料', '生成脚本', '检查脚本', '保存结果'];
  const done = events.findLast((ev) => ev.type === 'done');
  if (hasScript || done?.status === 'done') {
    return {
      title: '脚本已生成',
      detail: '脚本已保存并自动选中。你可以先确认或编辑脚本，再进入形象选择。',
      stages,
      activeIndex: 3,
      done: true,
    };
  }
  if (done && done.status !== 'done') {
    return {
      title: '生成未完成',
      detail: '本次没有产出可用脚本，请补充更明确的主题或素材链接后重试。',
      stages,
      activeIndex: 0,
      done: false,
    };
  }
  const actions = events.map((ev) => ev.action || ev.tool || '');
  const activeIndex =
    actions.some((a) => a === 'evaluate_script' || a === 'finish') ? 2 :
    actions.some((a) => a === 'generate_script') ? 1 :
    actions.some((a) => a === 'fetch_source' || a === 'summarize' || a === 'generate_topics' || a === 'fact_check') ? 0 :
    0;
  return {
    title: running ? '正在自动生成脚本' : '正在准备生成',
    detail: running ? '系统正在处理资料、生成脚本并检查质量。页面会在完成后显示脚本和下一步入口。' : '已收到创作目标，正在准备生成流程。',
    stages,
    activeIndex,
    done: false,
  };
}

function buildScriptVideoHref(projectId: string, scriptId: string): string {
  const href = projectHref('/workspace/video', projectId);
  if (!scriptId) return href;
  return `${href}${href.includes('?') ? '&' : '?'}script=${encodeURIComponent(scriptId)}`;
}

function buildScriptContentHref(projectId: string, scriptId: string): string {
  const href = projectHref('/workspace/content', projectId);
  if (!scriptId) return href;
  return `${href}${href.includes('?') ? '&' : '?'}script=${encodeURIComponent(scriptId)}`;
}
