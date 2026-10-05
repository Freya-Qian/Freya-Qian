'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { ArrowRight, Box, CheckCircle2, ImageUp, Sparkles, Trash2, Upload, UserRound } from 'lucide-react';
import {
  listProjects, createProject, deleteProject, listProfiles, createProfile, deleteProfile, listTemplates,
  Project, Profile, TemplateAvatar, uploadProfilePhoto, previewAvatar,
} from '@/lib/api/client';

import { useToast } from '@/components/toast';
import { BackStep } from '@/components/back-step';
import { ConfirmDialog } from '@/components/confirm-dialog';
import { getProjectFromUrl, getRememberedProject, projectHref, rememberProject } from '@/lib/project-url';
import { readWorkspaceDraft, saveWorkspaceDraft } from '@/lib/workspace-draft';

type ProfileForm = { name: string; style: string; topics: string; catch: string; banned: string; templateId: number };
type ProfileDraft = { newProjectName?: string; form?: ProfileForm; selectedProfileId?: string };
const emptyForm = { name: '', style: '', topics: '', catch: '', banned: '', templateId: 1 };

export default function ProfilePage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [current, setCurrent] = useState<Project | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [templates, setTemplates] = useState<TemplateAvatar[]>([]);
  const [newProj, setNewProj] = useState('');
  const [form, setForm] = useState<ProfileForm>(emptyForm);
  const [avatarMode, setAvatarMode] = useState<'template' | 'photo'>('template');
  const [photo, setPhoto] = useState<File | null>(null);
  const [photoConsent, setPhotoConsent] = useState(false);
  const [photoUrl, setPhotoUrl] = useState('');
  useEffect(() => {
    if (!photo) { setPhotoUrl(''); return; }
    const url = URL.createObjectURL(photo);
    setPhotoUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);
  const [previews, setPreviews] = useState<Record<string, string>>({});
  const [previewing, setPreviewing] = useState<Record<string, boolean>>({});
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [zoomTemplate, setZoomTemplate] = useState<TemplateAvatar | null>(null);
  const [success, setSuccess] = useState('');
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);
  const [profilesLoading, setProfilesLoading] = useState(false);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [pendingDelete, setPendingDelete] = useState<{ kind: 'profile'; item: Profile } | { kind: 'project'; item: Project } | null>(null);
  const [deleteError, setDeleteError] = useState('');
  const [previewErrors, setPreviewErrors] = useState<Record<string, string>>({});
  const mutation = useRef(false);
  const mounted = useRef(false);
  const generation = useRef(0);
  const activeProject = useRef<string | null>(null);
  const previewRequests = useRef(new Map<string, symbol>());
  const previewUrls = useRef<Record<string, string>>({});
  const busy = loading || profilesLoading || projectsLoading;
  const { show } = useToast();
  const successRef = useRef<HTMLDivElement | null>(null);
  const previewRef = useRef<HTMLDivElement | null>(null);
  const headingRef = useRef<HTMLHeadingElement | null>(null);

  function clearPreviews() {
    previewRequests.current.clear();
    Object.values(previewUrls.current).forEach((url) => URL.revokeObjectURL(url));
    previewUrls.current = {};
    setPreviews({});
    setPreviewing({});
    setPreviewErrors({});
  }

  function switchProject(project: Project | null) {
    generation.current += 1;
    activeProject.current = project?.id || null;
    clearPreviews();
    const saved = project ? readWorkspaceDraft<ProfileDraft>('profile', project.id) : null;
    setCurrent(project);
    setProfiles([]);
    setProfilesLoading(Boolean(project));
    setNewProj(saved?.newProjectName || '');
    setForm({ ...emptyForm, ...saved?.form });
    setSelectedProfileId(saved?.selectedProfileId || '');
    setSuccess('');
    setErr('');
    setZoomTemplate(null);
    setPhoto(null);
    setPhotoConsent(false);
    setAvatarMode('template');
    if (project) rememberProject(project.id);
  }

  function beginMutation() {
    if (mutation.current || profilesLoading || projectsLoading) return false;
    mutation.current = true;
    setLoading(true);
    setErr('');
    setSuccess('');
    return true;
  }

  function endMutation() {
    mutation.current = false;
    if (mounted.current) setLoading(false);
  }

  async function refreshProjects() {
    const epoch = generation.current;
    let list = await listProjects();
    if (!mounted.current || epoch !== generation.current) return;
    if (list.length === 0) {
      const created = await createProject('我的第一个项目');
      if (!mounted.current || epoch !== generation.current) return;
      list = [created];
      setSuccess('已为你创建默认项目。现在可以直接创建第一个数字人角色。');
    }
    setProjects(list);
    if (!activeProject.current && list.length) {
      const target = getProjectFromUrl() || getRememberedProject();
      const picked = list.find((p) => p.id === target) || list[0];
      switchProject(picked);
    }
  }

  async function refreshProfiles() {
    if (current) {
      const epoch = generation.current;
      try {
        const next = await listProfiles(current.id);
        if (epoch !== generation.current) return;
        setProfiles(next);
        const saved = readWorkspaceDraft<ProfileDraft>('profile', current.id);
        setSelectedProfileId((selected) => next.some((profile) => profile.id === selected) ? selected : saved?.selectedProfileId === '' ? '' : next[0]?.id || '');
        next.forEach((p) => { void loadPreview(p.id); });
      } catch (e) {
        if (epoch === generation.current) setErr(e instanceof Error ? e.message : '加载角色失败');
      } finally {
        if (epoch === generation.current) setProfilesLoading(false);
      }
    }
  }

  async function loadPreview(profileId: string, options: { force?: boolean; notify?: boolean; focus?: boolean } = {}) {
    if (previewRequests.current.has(profileId)) return false;
    const epoch = generation.current;
    const request = Symbol(profileId);
    previewRequests.current.set(profileId, request);
    const valid = () => epoch === generation.current && previewRequests.current.get(profileId) === request;
    if (options.focus) {
      setSelectedProfileId(profileId);
      setSuccess('');
      previewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    setPreviewErrors((p) => ({ ...p, [profileId]: '' }));
    setPreviewing((p) => ({ ...p, [profileId]: true }));
    try {
      const url = await previewAvatar(profileId, Boolean(options.force));
      if (!valid()) { URL.revokeObjectURL(url); return false; }
      if (previewUrls.current[profileId]) URL.revokeObjectURL(previewUrls.current[profileId]);
      previewUrls.current = { ...previewUrls.current, [profileId]: url };
      setPreviews(previewUrls.current);
      if (options.notify) {
        show('success', '3D 预览已刷新');
      }
      return true;
    } catch (e) {
      if (valid()) setPreviewErrors((p) => ({ ...p, [profileId]: e instanceof Error ? e.message : '刷新预览失败' }));
      return false;
    } finally {
      if (valid()) {
        previewRequests.current.delete(profileId);
        setPreviewing((p) => ({ ...p, [profileId]: false }));
      }
    }
  }

  useEffect(() => {
    let cancelled = false;
    mounted.current = true;
    const requests = previewRequests.current;
    Promise.resolve().then(() => {
      if (cancelled) return;
      refreshProjects().catch((e) => { if (!cancelled) setErr(e.message); })
        .finally(() => { if (!cancelled) setProjectsLoading(false); });
      listTemplates().then((list) => { if (!cancelled) setTemplates(list); })
        .catch((e) => { if (!cancelled) setErr(e.message); });
    });
    return () => {
      cancelled = true;
      mounted.current = false;
      generation.current += 1;
      requests.clear();
      Object.values(previewUrls.current).forEach((url) => URL.revokeObjectURL(url));
      previewUrls.current = {};
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    Promise.resolve().then(() => {
      refreshProfiles().catch((e) => setErr(e.message));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current]);

  useEffect(() => {
    if (!current || profilesLoading) return;
    saveWorkspaceDraft<ProfileDraft>('profile', current.id, {
      newProjectName: newProj,
      form,
      selectedProfileId,
    });
  }, [current, form, newProj, selectedProfileId, profilesLoading]);

  const handleCreateProject = async () => {
    if (!newProj.trim() || !beginMutation()) return;
    try {
      const p = await createProject(newProj.trim());
      if (!mounted.current) return;
      setProjects((list) => [...list, p]);
      switchProject(p);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '新建失败');
    } finally {
      endMutation();
    }
  };

  const handleDeleteProject = async (project: Project) => {
    if (!beginMutation()) return;
    setDeleteError('');
    try {
      await deleteProject(project.id);
      if (!mounted.current) return;
      const nextProjects = projects.filter((p) => p.id !== project.id);
      setProjects(nextProjects);
      if (activeProject.current === project.id) switchProject(nextProjects[0] || null);
      setPendingDelete(null);
      setSuccess(`项目「${project.name}」已删除。`);
      show('success', `项目「${project.name}」已删除`);
      if (nextProjects.length === 0) {
        try {
          const created = await createProject('我的第一个项目');
          if (!mounted.current) return;
          setProjects([created]);
          switchProject(created);
          setSuccess(`项目「${project.name}」已删除，已创建新的默认项目。`);
        } catch {
          setErr('项目已删除，但默认项目创建失败。请手动新建项目。');
        }
      }
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : '删除项目失败');
    } finally {
      endMutation();
    }
  };

  const handleCreateProfile = async () => {
    if (avatarMode === 'photo' && (!photo || !photoConsent)) return;
    if (!current || !form.name.trim() || !beginMutation()) return;
    try {
      const created = await createProfile(current.id, {
        name: form.name.trim(),
        style_tags: form.style.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
        topic_preferences: form.topics.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
        catchphrases: form.catch.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
        banned_phrases: form.banned.split(/[,，]/).map((s) => s.trim()).filter(Boolean),
        language: 'zh',
        avatar_type: 'template',
        template_id: form.templateId,
        voice_type: 'default_tts',
        video_ratio: '9:16',
        platform_preferences: ['douyin'],
      });
      if (!mounted.current) return;
      setForm({ ...emptyForm, templateId: created.template_id });
      setProfiles((list) => [...list, created]);
      setSelectedProfileId(created.id);
      if (avatarMode === 'photo' && photo) {
        try {
          const updated = await uploadProfilePhoto(created.id, photo);
          setProfiles((list) => list.map((item) => item.id === created.id ? updated : item));
          setPhoto(null);
          setPhotoConsent(false);
        } catch (error) {
          setErr(`角色已创建，但照片上传失败，请在角色列表重试：${error instanceof Error ? error.message : '上传失败'}`);
          return;
        }
      }
      setSuccess(`角色「${created.name}」创建成功。`);
      show('success', `数字人「${created.name}」已创建`);
      setTimeout(() => successRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 60);
      void loadPreview(created.id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : '创建失败');
    } finally {
      endMutation();
    }
  };

  const handleUpload = async (profileId: string, file: File) => {
    if (!profiles.some((p) => p.id === profileId) || !beginMutation()) return;
    // Invalidate an older preview before uploading a replacement photo.
    previewRequests.current.delete(profileId);
    setSelectedProfileId(profileId);
    setTimeout(() => previewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 40);
    try {
      setPreviewing((p) => ({ ...p, [profileId]: true }));
      const updated = await uploadProfilePhoto(profileId, file);
      if (!mounted.current) return;
      setProfiles((list) => list.map((p) => p.id === profileId ? updated : p));
      if (previewUrls.current[profileId]) URL.revokeObjectURL(previewUrls.current[profileId]);
      delete previewUrls.current[profileId];
      setPreviews({ ...previewUrls.current });
      const ready = await loadPreview(profileId, { force: true });
      if (!mounted.current) return;
      if (ready) {
        setSuccess('本人照片已上传，3D 风格化预览已更新。');
        show('success', '照片已上传，3D 渲染风预览已更新');
      } else {
        setErr('照片已上传，但 3D 预览未完成。请重试刷新预览。');
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : '上传失败');
    } finally {
      setPreviewing((p) => ({ ...p, [profileId]: false }));
      endMutation();
    }
  };

  const handleDeleteProfile = async (profile: Profile) => {
    if (!profiles.some((p) => p.id === profile.id) || !beginMutation()) return;
    setDeleteError('');
    try {
      await deleteProfile(profile.id);
      if (!mounted.current) return;
      previewRequests.current.delete(profile.id);
      if (previewUrls.current[profile.id]) URL.revokeObjectURL(previewUrls.current[profile.id]);
      delete previewUrls.current[profile.id];
      setPreviews({ ...previewUrls.current });
      setPreviewing((p) => ({ ...p, [profile.id]: false }));
      const remaining = profiles.filter((p) => p.id !== profile.id);
      setProfiles(remaining);
      setSelectedProfileId((selected) => selected === profile.id ? remaining[0]?.id || '' : selected);
      setPendingDelete(null);
      setSuccess(`角色「${profile.name}」已删除。`);
      show('success', `角色「${profile.name}」已删除`);
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : '删除失败');
    } finally {
      endMutation();
    }
  };

  const selectedProfile = profiles.find((p) => p.id === selectedProfileId) || null;
  const selectedTemplate = selectedProfile?.avatar_type === 'uploaded_self' ? undefined : templates.find((t) => t.id === (selectedProfile?.template_id ?? form.templateId));
  const previewReady = Boolean(selectedProfile && !busy && !previewing[selectedProfile.id] && !previewErrors[selectedProfile.id] && (previews[selectedProfile.id] || selectedTemplate));
  const nextHref = projectHref('/workspace/content', current?.id);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 ref={headingRef} tabIndex={-1} className="title">我的角色</h1>
        </div>
        <BackStep fallbackHref={projectHref('/workspace', current?.id)} />
      </div>

      {/* 项目选择 */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="muted">当前项目：</span>
          {projects.map((p) => (
            <div key={p.id} className="row" style={{ gap: 4 }}>
              <button
                className="btn btn-ghost"
                style={current?.id === p.id ? { borderColor: 'var(--primary)', color: 'var(--primary)' } : {}}
                disabled={busy}
                onClick={() => {
                  if (!mutation.current && !profilesLoading && current?.id !== p.id) switchProject(p);
                }}
              >
                {p.name}
              </button>
              <button
                className="btn btn-ghost danger-btn"
                style={{ minHeight: 38, padding: '7px 9px' }}
                title={`删除项目 ${p.name}`}
                aria-label={`删除项目 ${p.name}`}
                disabled={busy}
                onClick={() => {
                  if (mutation.current || profilesLoading) return;
                  setDeleteError('');
                  setPendingDelete({ kind: 'project', item: p });
                }}
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
          <input disabled={busy} className="input" style={{ width: 140 }} value={newProj} onChange={(e) => setNewProj(e.target.value)} placeholder="新项目名" />
          <button className="btn" disabled={busy || !newProj.trim()} onClick={handleCreateProject}>新建项目</button>
        </div>
      </div>

      {err && <div role="alert" className="err" style={{ marginBottom: 16 }}>{err}</div>}

      {success && (
        <div ref={successRef} className="card profile-next-card" style={{ marginBottom: 16 }}>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
            <div className="row" style={{ flex: '1 1 260px' }}>
              <CheckCircle2 size={20} style={{ color: 'var(--success)' }} />
              <div>
                <div style={{ fontWeight: 720 }}>操作结果</div>
                <div className="muted">{success}</div>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="grid-2" style={{ marginBottom: 12 }}>
        <div className="profile-create" style={{ padding: 12 }}>
          <h2 style={{ fontSize: 15, margin: '0 0 10px' }}>新建角色</h2>
          <div style={{ display: 'grid', gap: 9 }}>
            <div>
              <label className="label">名称</label>
              <input disabled={busy} className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="如：小 A" />
            </div>
            <div className="profile-form-grid">
              <div>
                <label className="label">表达风格（逗号分隔）</label>
                <input disabled={busy} className="input" value={form.style} onChange={(e) => setForm({ ...form, style: e.target.value })} placeholder="专业、犀利" />
              </div>
              <div>
                <label className="label">内容方向（逗号分隔）</label>
                <input disabled={busy} className="input" value={form.topics} onChange={(e) => setForm({ ...form, topics: e.target.value })} placeholder="AI 工具、AI 产品" />
              </div>
              <div>
                <label className="label">口头禅（逗号分隔）</label>
                <input disabled={busy} className="input" value={form.catch} onChange={(e) => setForm({ ...form, catch: e.target.value })} placeholder="关注我不迷路" />
              </div>
              <div>
                <label className="label">禁用词（逗号分隔）</label>
                <input disabled={busy} className="input" value={form.banned} onChange={(e) => setForm({ ...form, banned: e.target.value })} placeholder="全球第一" />
              </div>
            </div>
            <div className="avatar-source-tabs" role="group" aria-label="角色形象来源">
              <button className="btn" aria-pressed={avatarMode === 'template'} disabled={busy} onClick={() => setAvatarMode('template')}>使用模板</button>
              <button className="btn" aria-pressed={avatarMode === 'photo'} disabled={busy} onClick={() => setAvatarMode('photo')}><ImageUp size={16} /> 上传照片</button>
            </div>
            {avatarMode === 'photo' && <div className="photo-create-field">
              <label className="photo-picker" htmlFor="new-role-photo" aria-disabled={busy}>
                <span className="photo-picker-visual">
                  {/* Local object URL preserves the original photo preview. */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {photoUrl ? <img src={photoUrl} alt="已选择的本人照片" /> : <ImageUp size={24} aria-hidden="true" />}
                </span>
                <span className="photo-picker-copy"><strong>{photo ? photo.name : '上传本人照片'}</strong><span>{photo ? `${(photo.size / 1024 / 1024).toFixed(1)} MB · 点击更换` : 'JPG、PNG、WebP · 最大 10 MB'}</span></span>
                <span className="photo-picker-action">{photo ? '更换照片' : '选择照片'}</span>
              <input id="new-role-photo" className="photo-picker-input" aria-label="上传本人照片" type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={(event) => {
                const file = event.target.files?.[0];
                if (file && (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024)) {
                  setErr('请选择 10 MB 以内的 JPG、PNG 或 WebP 图片。');
                  event.target.value = '';
                  setPhoto(null);
                  return;
                }
                setErr('');
                setPhoto(file || null);
              }} />
              </label>
              <label className="photo-consent"><input type="checkbox" checked={photoConsent} disabled={busy} onChange={(event) => setPhotoConsent(event.target.checked)} />确认是本人照片，并授权用于本产品的数字人创作</label>
            </div>}
            {avatarMode === 'template' && templates.length > 0 && (
              <div>
                <label className="label">默认模板形象</label>
                <div className="template-picker">
                  {templates.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      disabled={busy}
                      className={`template-option ${form.templateId === t.id ? 'active' : ''}`}
                      title={`${t.name}，双击放大`}
                      aria-pressed={form.templateId === t.id}
                      onClick={() => {
                        if (mutation.current || profilesLoading) return;
                        setForm({ ...form, templateId: t.id });
                        setSelectedProfileId('');
                        setSuccess('');
                      }}
                      onDoubleClick={(e) => {
                        e.preventDefault();
                        setZoomTemplate(t);
                      }}
                    >
                      <img src={t.image_url} alt={t.name} loading="lazy" />
                      <span>{t.name}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="form-action">
              <button className="btn action-primary" onClick={handleCreateProfile} disabled={busy || !current || !form.name.trim() || (avatarMode === 'photo' && (!photo || !photoConsent))}>
                {loading ? <span className="spin" /> : <Upload size={16} />}
                {loading ? '正在处理' : current ? '创建角色' : '请先新建项目'}
              </button>
            </div>
          </div>
        </div>

        <div className="card" style={{ padding: 12 }} ref={previewRef}>
          <h2 style={{ fontSize: 15, margin: '0 0 10px' }}>3D 风格化预览</h2>
          <div className="preview-stage">
            {selectedProfile && previews[selectedProfile.id] ? (
              <img src={previews[selectedProfile.id]} alt="3D 风格化数字人预览" />
            ) : selectedTemplate ? (
              <div className="template-preview">
                <img src={selectedTemplate.image_url} alt={`${selectedTemplate.name} 模板预览`} />
                <span>{selectedProfile ? `${selectedProfile.name} 使用的默认模板` : '当前选择的默认模板'}</span>
              </div>
            ) : (
              <div className="muted" style={{ textAlign: 'center', padding: 24 }}>
                <Box size={34} style={{ color: 'var(--primary)', marginBottom: 8 }} />
                <div>{selectedProfile?.avatar_type === 'uploaded_self' ? '本人形象预览尚未就绪，请刷新预览' : selectedProfile ? '正在准备预览，或点击刷新 3D 预览' : '创建角色后显示预览'}</div>
              </div>
            )}
            {selectedProfile && previewing[selectedProfile.id] && (
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  display: 'grid',
                  placeItems: 'center',
                  background: 'rgba(8, 12, 18, 0.58)',
                  backdropFilter: 'blur(2px)',
                }}
              >
                <div className="tag" style={{ color: 'var(--primary)', background: 'rgba(20, 27, 38, 0.9)' }}>
                  <span className="spin" /> 正在生成 3D 渲染风预览
                </div>
              </div>
            )}
          </div>
          {selectedProfile && previewErrors[selectedProfile.id] && <p className="err" role="alert">{previewErrors[selectedProfile.id]}</p>}
          {selectedProfile && (
            <div className="profile-preview-footer">
              <div className="profile-preview-identity">
                <strong>{selectedProfile.name}</strong>
                <span className="muted">{previewReady ? '形象已就绪' : '形象预览尚未就绪'}</span>
              </div>
              {previewReady && <Link className="btn btn-primary profile-continue" href={nextHref}>
                下一步：选题与脚本 <ArrowRight size={16} />
              </Link>}
            </div>
          )}
        </div>
      </div>

      {/* Profile 列表 */}
      <div className="profile-library" style={{ marginBottom: 12, padding: 12 }}>
        <h2 style={{ fontSize: 15, margin: '0 0 10px' }}>已创建角色 · {profiles.length}</h2>
        {profilesLoading && <p role="status" className="muted">正在加载角色…</p>}
        {!profilesLoading && profiles.length === 0 && (
          <div className="card" style={{ background: 'var(--surface-2)' }}>
            <div style={{ fontWeight: 700 }}>先创建一个角色</div>
            <div className="muted" style={{ marginTop: 4 }}>角色决定脚本口吻、内容方向和视频形象。填完下方表单后，这里会显示创建结果。</div>
          </div>
        )}
        {[
          { key: 'current', title: '当前角色', items: profiles.filter((p) => p.id === selectedProfile?.id) },
          { key: 'history', title: '历史角色', items: profiles.filter((p) => p.id !== selectedProfile?.id) },
        ].filter((group) => group.items.length > 0).map((group) => (
          <section key={group.key} className="profile-role-group" aria-labelledby={`roles-${group.key}`}>
            <h3 id={`roles-${group.key}`} className="profile-group-title">{group.title}<span>{group.items.length}</span></h3>
            {group.items.map((p) => (
          <div
            key={p.id}
            className="card"
            style={{
              marginBottom: 10,
              background: 'var(--surface-2)',
              borderColor: selectedProfile?.id === p.id ? 'var(--primary)' : 'var(--border)',
            }}
            onClick={() => {
              if (mutation.current || profilesLoading) return;
              setSelectedProfileId(p.id);
              setSuccess('');
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <UserRound size={18} style={{ color: 'var(--primary)' }} />
              <button type="button" className="btn btn-ghost" disabled={busy} aria-pressed={selectedProfile?.id === p.id}
                onClick={(event) => {
                  event.stopPropagation();
                  if (mutation.current || profilesLoading) return;
                  setSelectedProfileId(p.id);
                  setSuccess('');
                }}>{p.name}</button>
              {selectedProfile?.id === p.id && <span className="tag" style={{ color: 'var(--primary)' }}>当前角色</span>}
              {p.avatar_type === 'uploaded_self' && <span className="tag" style={{ color: 'var(--success)' }}>已上传照片</span>}
              {p.avatar_type !== 'uploaded_self' && <span className="tag">模板 {p.template_id || 1}</span>}
              {(p.style_tags || []).map((s) => <span key={s} className="tag">{s}</span>)}
              <button
                className="btn btn-ghost"
                style={{ marginLeft: 'auto', minHeight: 32, padding: '5px 9px', color: 'var(--danger)' }}
                onClick={(e) => {
                  e.stopPropagation();
                  if (mutation.current || profilesLoading) return;
                  setDeleteError('');
                  setPendingDelete({ kind: 'profile', item: p });
                }}
                disabled={busy}
                title={`删除角色 ${p.name}`}
                aria-label={`删除角色 ${p.name}`}
              >
                <Trash2 size={15} /> 删除
              </button>
            </div>
            <div className="muted" style={{ marginTop: 6 }}>
              方向：{(p.topic_preferences || []).join('、') || '未设置'} ｜ 禁用：{(p.banned_phrases || []).join('、') || '无'}
            </div>

            <div style={{ marginTop: 10 }}>
              <div className="muted" style={{ marginBottom: 6 }}>本人照片：</div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <label className="btn btn-ghost" aria-disabled={busy} style={{ cursor: 'pointer' }} onClick={(event) => event.stopPropagation()}>
                  <ImageUp size={16} /> 上传本人照片
                  <input
                    type="file"
                    disabled={busy}
                    accept="image/jpeg,image/png,image/webp"
                    style={{ display: 'none' }}
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      e.currentTarget.value = '';
                      if (!mutation.current && !profilesLoading && f && window.confirm('确认上传的是本人形象并授权在本产品内使用？')) void handleUpload(p.id, f);
                    }}
                  />
                </label>
              </div>
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              <button
                className="btn btn-ghost"
                onClick={(e) => {
                  e.stopPropagation();
                  if (mutation.current || profilesLoading) return;
                  void loadPreview(p.id, { force: true, notify: true, focus: true });
                }}
                disabled={busy || previewing[p.id]}
              >
                {previewing[p.id] ? <span className="spin" /> : <Sparkles size={16} />} 刷新 3D 预览
              </button>
              <span className="muted">上传本人照片后会展示风格化结果；未上传时使用创建角色时选择的模板。</span>
            </div>
          </div>
            ))}
          </section>
        ))}
      </div>
      <ConfirmDialog
        fallbackFocusRef={headingRef}
        open={Boolean(pendingDelete)}
        title={pendingDelete ? `删除${pendingDelete.kind === 'profile' ? '角色' : '项目'}「${pendingDelete.item.name}」？` : ''}
        description={pendingDelete?.kind === 'project' ? '项目下的角色、信息源、选题、脚本、视频任务和素材都会一起删除。此操作无法撤销。' : '删除后不能继续用该角色生成视频。此操作无法撤销。'}
        busy={loading}
        error={deleteError}
        onCancel={() => { if (!mutation.current) setPendingDelete(null); }}
        onConfirm={() => {
          if (pendingDelete?.kind === 'profile') void handleDeleteProfile(pendingDelete.item);
          if (pendingDelete?.kind === 'project') void handleDeleteProject(pendingDelete.item);
        }}
      />
      {zoomTemplate && (
        <div
          role="dialog"
          aria-modal="true"
          className="image-modal"
          onClick={() => setZoomTemplate(null)}
        >
          <div className="image-modal-inner" onClick={(e) => e.stopPropagation()}>
            <img src={zoomTemplate.image_url} alt={zoomTemplate.name} />
            <div className="row" style={{ justifyContent: 'space-between', marginTop: 10 }}>
              <span>{zoomTemplate.name}</span>
              <button className="btn btn-ghost" onClick={() => setZoomTemplate(null)}>关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
