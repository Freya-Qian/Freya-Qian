'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { ArrowRight, CheckCircle2, Link2, Sparkles, FileText, Trash2, Clock3 } from 'lucide-react';
import {
  listProjects, createProject, listSources, createSource, fetchSource, listItems, summarizeItem, createTopics, listTopics,
  streamScript, deleteSource, deleteItem, deleteTopic, listScripts, updateScript, exportScript, downloadText,
  Project, Source, Item, Topic, Script,
} from '@/lib/api/client';
import { useToast } from '@/components/toast';
import { BackStep } from '@/components/back-step';
import { getProjectFromUrl, getRememberedProject, projectHref, rememberProject } from '@/lib/project-url';
import { readWorkspaceDraft, saveWorkspaceDraft } from '@/lib/workspace-draft';

type ContentDraft = {
  sourceUrl?: string;
  currentSourceId?: string;
  currentItemIds?: string[];
  selectedTopicId?: string;
  scriptId?: string;
  editedContent?: string;
};

export default function ContentPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState('');
  const [sources, setSources] = useState<Source[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [url, setUrl] = useState('');
  const [script, setScript] = useState<Script | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState('');
  const [success, setSuccess] = useState('');
  const [currentSourceId, setCurrentSourceId] = useState('');
  const [selectedTopicId, setSelectedTopicId] = useState('');
  const [taskItemIds, setTaskItemIds] = useState<string[]>([]);
  const [editedContent, setEditedContent] = useState('');
  const [streamText, setStreamText] = useState('');
  const [historyTab, setHistoryTab] = useState<'sources' | 'topics'>('sources');
  const operationRef = useRef(false);
  const loadRef = useRef(0);
  const restoredProjectRef = useRef('');
  const { show } = useToast();

  async function refreshProjects() {
    let list = await listProjects();
    if (list.length === 0) {
      const created = await createProject('我的第一个项目');
      list = [created];
      setSuccess('已为你创建默认项目。粘贴链接后按回车，即可自动抓取并生成主题。');
    }
    setProjects(list);
    if (list.length && !projectId) {
      const target = getProjectFromUrl() || getRememberedProject();
      const picked = list.find((p) => p.id === target) || list[0];
      await handleProject(picked.id, true);
    }
  }
  async function refreshSources() {
    setSources(await listSources());
  }
  async function refreshItems() {
    setItems(await listItems());
  }
  async function refreshTopics() {
    setTopics(await listTopics());
  }

  async function refreshContent() {
    await Promise.all([refreshSources(), refreshItems(), refreshTopics()]);
  }

  useEffect(() => {
    Promise.resolve().then(() => {
      refreshProjects().catch((e) => setErr(e.message));
      refreshContent().catch((e) => setErr(e.message));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!projectId || restoredProjectRef.current !== projectId) return;
    let cancelled = false;
    Promise.resolve().then(() => saveWorkspaceDraft<ContentDraft>('content', projectId, {
      sourceUrl: url,
      currentSourceId, currentItemIds: taskItemIds, selectedTopicId,
      scriptId: script?.id, editedContent,
    })).catch(() => { if (!cancelled) setErr('浏览器无法保存当前任务，请检查本地存储空间。'); });
    return () => { cancelled = true; };
  }, [projectId, url, currentSourceId, taskItemIds, selectedTopicId, script, editedContent]);

  async function run<T>(label: string, fn: () => Promise<T>): Promise<T | undefined> {
    if (operationRef.current) return;
    operationRef.current = true;
    setErr('');
    setBusy(label);
    try {
      return await fn();
    } catch (e) {
      setErr(e instanceof Error ? e.message : '操作失败');
      return undefined;
    } finally {
      operationRef.current = false;
      setBusy('');
    }
  }

  const handleAddSource = async () => {
    if (!projectId || !url.trim()) return;
    const result = await run('自动生成选题', async () => {
      selectTopic('');
      setTaskItemIds([]);
      const source = await createSource({ project_id: projectId, source_type: 'url', url: url.trim() });
      setCurrentSourceId(source.id);
      setSources((prev) => [source, ...prev]);
      setSuccess('链接已添加，正在抓取内容并生成主题。');
      const fetchedItems = await fetchSource(source.id);
      setTaskItemIds(fetchedItems.map((item) => item.id));
      await refreshItems();
      const summarizedItems: Item[] = [];
      for (const item of fetchedItems) {
        summarizedItems.push(await summarizeItem(item.id));
      }
      const topicGroups: Topic[] = [];
      for (const item of summarizedItems) {
        topicGroups.push(...await createTopics(item.id));
      }
      await Promise.all([refreshSources(), refreshItems(), refreshTopics()]);
      return { source, fetchedItems, topics: topicGroups };
    });
    if (result) {
      setUrl('');
      setSelectedTopicId('');
      if (result.fetchedItems.length === 0) {
        setSuccess('链接已添加，但没有抓到新内容。可能是历史中已抓取过，可查看历史抓取或删除后重试。');
        show('error', '没有抓到新内容');
      } else {
        setSuccess(`已从当前链接抓取 ${result.fetchedItems.length} 条内容，并生成 ${result.topics.length} 个候选主题。下一步选择主题生成脚本。`);
        show('success', `已生成 ${result.topics.length} 个候选主题`);
      }
    }
  };

  const handleProject = async (id: string, initial = false) => {
    if (operationRef.current) return;
    const request = ++loadRef.current;
    restoredProjectRef.current = '';
    const saved = readWorkspaceDraft<ContentDraft>('content', id);
    setProjectId(id);
    setUrl(saved?.sourceUrl || '');
    setScript(null);
    setEditedContent('');
    setStreamText('');
    setErr('');
    setSuccess('');
    setCurrentSourceId(saved?.currentSourceId || '');
    setTaskItemIds(saved?.currentItemIds || []);
    setSelectedTopicId(saved?.selectedTopicId || '');
    const target = initial ? new URLSearchParams(window.location.search).get('script') : null;
    if (!initial) {
      const location = new URL(window.location.href);
      location.searchParams.delete('script');
      window.history.replaceState(null, '', location.pathname + location.search);
    }
    rememberProject(id);
    setBusy('恢复任务');
    operationRef.current = true;
    try {
      const scripts = await listScripts(id);
      if (request !== loadRef.current) return;
      const restored = scripts.find((s) => s.id === (target || saved?.scriptId));
      if (restored) {
        setScript(restored);
        setSelectedTopicId(restored.topic_id);
        setEditedContent(restored.id === saved?.scriptId ? saved.editedContent ?? restored.content : restored.content);
      } else if (target) setErr('指定脚本不存在或不属于当前项目。');
      restoredProjectRef.current = id;
    } catch (e) {
      setErr(e instanceof Error ? e.message : '恢复任务失败');
    } finally {
      operationRef.current = false;
      setBusy('');
    }
  };

  function selectTopic(id: string) {
    setSelectedTopicId(id);
    setScript(null);
    setEditedContent('');
    setStreamText('');
    setSuccess('');
    const location = new URL(window.location.href);
    location.searchParams.delete('script');
    window.history.replaceState(null, '', location.pathname + location.search);
  }

  const handleFetch = async (id: string) => {
    if (operationRef.current) return;
    selectTopic('');
    setCurrentSourceId(id);
    setTaskItemIds([]);
    const result = await run('自动生成选题', async () => {
      const r = await fetchSource(id);
      setTaskItemIds(r.map((item) => item.id));
      await refreshItems();
      const summarizedItems: Item[] = [];
      for (const item of r) {
        summarizedItems.push(await summarizeItem(item.id));
      }
      const topicGroups: Topic[] = [];
      for (const item of summarizedItems) {
        topicGroups.push(...await createTopics(item.id));
      }
      await Promise.all([refreshItems(), refreshTopics()]);
      return { items: r, topics: topicGroups };
    });
    if (result) {
      setSelectedTopicId('');
      if (result.items.length === 0) {
        show('error', '没有抓到新内容（可能已抓取过）');
      } else {
        setSuccess(`当前信息源已抓取 ${result.items.length} 条内容，并生成 ${result.topics.length} 个候选主题。`);
        show('success', `已生成 ${result.topics.length} 个候选主题`);
      }
    }
  };

  const handleSummarize = async (id: string) => {
    const ok = await run('摘要', async () => {
      await summarizeItem(id);
      await refreshItems();
      return true;
    });
    if (ok) {
      setSuccess('摘要已生成。下一步点击「生成主题」。');
      show('success', '摘要已生成，点「生成主题」');
    }
  };

  const handleTopics = async (itemId: string) => {
    if (operationRef.current) return;
    selectTopic('');
    setTaskItemIds([itemId]);
    const item = items.find((entry) => entry.id === itemId);
    const source = sources.find((entry) => entry.project_id === projectId && item &&
      ((entry.url && entry.url === item.original_url) || (entry.name && entry.name === item.source_name) || (entry.url && entry.url === item.source_name)));
    setCurrentSourceId(source?.id || '');
    const ts = await run('生成选题', async () => {
      const created = await createTopics(itemId);
      await refreshTopics();
      return created;
    });
    if (ts) {
      setSelectedTopicId('');
      setSuccess('候选主题已生成。先挑一个角度生成脚本；脚本完成后，到「形象与视频」页选择数字人形象。');
      show('success', `已生成 ${ts.length} 个候选主题`);
    }
  };

  const handleGenerateScript = async (topicId: string) => {
    if (operationRef.current) return;
    operationRef.current = true;
    setStreaming(true);
    setScript(null);
    setEditedContent('');
    setStreamText('');
    setErr('');
    let completed = false;
    try {
      for await (const ev of streamScript(topicId)) {
        if (ev.delta) setStreamText((text) => text + ev.delta);
        if (ev.script) {
          completed = true;
          setScript(ev.script);
          setEditedContent(ev.script.content);
          setSuccess('脚本已生成并保存为草稿。下一步到「形象与视频」页确认脚本、选择出镜形象，再生成视频。');
          show('success', '脚本已生成');
        } else if (ev.error) {
          throw new Error(ev.error);
        }
      }
      if (!completed) throw new Error('生成中断，脚本尚未保存，请重试。');
    } catch (e) {
      setErr(e instanceof Error ? e.message : '生成脚本失败');
    } finally {
      operationRef.current = false;
      setStreaming(false);
    }
  };

  const handleExport = (format: 'md' | 'txt') => run('导出脚本', async () => {
    if (!script) return;
    if (editedContent !== script.content) setScript(await updateScript(script.id, editedContent));
    const result = await exportScript(script.id, format);
    await downloadText(result.content, `script-${script.id}.${format}`, format === 'txt' ? 'text/plain;charset=utf-8' : 'text/markdown;charset=utf-8');
  });

  const handleDeleteSource = async (source: Source) => {
    if (operationRef.current) return;
    if (!window.confirm(`确认删除信息源「${source.name || source.url}」？它抓取出的条目、主题、脚本和视频任务也会一起删除。`)) return;
    const ok = await run('删除信息源', async () => {
      await deleteSource(source.id);
      if (source.id === currentSourceId) {
        setCurrentSourceId('');
        setTaskItemIds([]);
        selectTopic('');
      } else {
        const remaining = await listScripts(projectId);
        if (script && !remaining.some((entry) => entry.id === script.id)) selectTopic('');
      }
      await refreshContent();
      return true;
    });
    if (ok) {
      setSuccess('信息源及它生成的内容已删除。你可以继续添加新的链接。');
      show('success', '信息源已删除');
    }
  };

  const handleDeleteItem = async (item: Item) => {
    if (operationRef.current) return;
    if (!window.confirm(`确认删除条目「${item.title || item.original_url}」？相关主题、脚本和视频任务也会一起删除。`)) return;
    const ok = await run('删除条目', async () => {
      await deleteItem(item.id);
      setTaskItemIds((ids) => ids.filter((id) => id !== item.id));
      if (topics.some((topic) => topic.source_item_id === item.id && (topic.id === selectedTopicId || topic.id === script?.topic_id))) selectTopic('');
      await refreshContent();
      return true;
    });
    if (ok) {
      setSuccess('条目及它生成的内容已删除。');
      show('success', '条目已删除');
    }
  };

  const handleDeleteTopic = async (topic: Topic) => {
    if (operationRef.current) return;
    if (!window.confirm(`确认删除主题「${topic.title}」？相关脚本和视频任务也会一起删除。`)) return;
    const ok = await run('删除主题', async () => {
      await deleteTopic(topic.id);
      if (selectedTopicId === topic.id || script?.topic_id === topic.id) selectTopic('');
      await refreshContent();
      return true;
    });
    if (ok) {
      setSuccess('主题及它生成的内容已删除。');
      show('success', '主题已删除');
    }
  };

  const projectSources = sources.filter((source) => source.project_id === projectId);
  const currentSources = projectSources.filter((source) => source.id === currentSourceId);
  const historySources = projectSources.filter((source) => source.id !== currentSourceId);
  const isAutoRunning = busy === '自动生成选题';
  const currentSource = currentSources[0] || null;
  const currentItems = items.filter((item) => taskItemIds.includes(item.id));
  const currentItemIds = new Set(currentItems.map((item) => item.id));
  const currentTopics = currentItemIds.size > 0 ? topics.filter((topic) => currentItemIds.has(topic.source_item_id)) : [];
  const historyItems = items.filter((item) => !currentItemIds.has(item.id) && projectSources.some((source) =>
    (source.url && item.original_url === source.url) || (source.name && item.source_name === source.name) || (source.url && item.source_name === source.url)));
  const currentTopicIds = new Set(currentTopics.map((topic) => topic.id));
  const historyTopics = topics.filter((topic) => !currentTopicIds.has(topic.id) && historyItems.some((item) => item.id === topic.source_item_id));
  const selectedTopic = topics.find((topic) => topic.id === selectedTopicId) || null;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="title">选题与脚本</h1>
        </div>
        <BackStep fallbackHref={projectHref('/workspace/profile', projectId)} />
      </div>

      {/* 项目选择 */}
      <div className="project-toolbar" style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="muted">项目：</span>
          {projects.map((p) => (
            <button key={p.id} disabled={Boolean(busy) || streaming} className="btn btn-ghost" style={projectId === p.id ? { borderColor: 'var(--primary)', color: 'var(--primary)' } : {}} onClick={() => handleProject(p.id)}>
              {p.name}
            </button>
          ))}
        </div>
      </div>

      {err && <div className="err" style={{ marginBottom: 12 }}>{err}</div>}

      <fieldset disabled={Boolean(busy) || streaming} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
      <div className="content-workbench">
        <section className="card content-intake-panel">
          <h2 className="panel-title">当前任务</h2>
          <form
            className="source-submit"
            onSubmit={(event) => {
              event.preventDefault();
              handleAddSource();
            }}
          >
            <input className="input" aria-label="文章或帖子链接" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="粘贴文章或帖子链接" />
            <button className="btn btn-primary" type="submit" disabled={isAutoRunning || !url.trim()}>
              {isAutoRunning ? <span className="spin" /> : <Link2 size={16} />}
              {isAutoRunning ? '正在生成' : '生成主题'}
            </button>
          </form>
          {success && (
            <div className="status-strip">
              <CheckCircle2 size={18} />
              <span>{success}</span>
            </div>
          )}
        </section>

        <section className="card content-current-panel">
          <div className="section-heading">
            <div>
              <h2 className="panel-title">当前抓取</h2>
            </div>
            {currentSource && <span className="tag">当前来源 · {currentSource.source_type}</span>}
          </div>
          {!currentSource && (
            <EmptyBlock title="暂无抓取内容" />
          )}
          {currentSource && currentItems.length === 0 && (
            <SourceSection title="当前来源" sources={[currentSource]} busy={busy} onFetch={handleFetch} onDelete={handleDeleteSource} />
          )}

          {currentItems.length > 0 && (
            <div className="result-stack">
              {currentItems.map((item) => (
                <ItemRow key={item.id} item={item} busy={busy} onSummarize={handleSummarize} onTopics={handleTopics} onDelete={handleDeleteItem} />
              ))}
            </div>
          )}

        </section>
      </div>

      <section className="card topic-module">
        <div className="section-heading">
          <div>
            <h2 className="panel-title">本次候选主题</h2>
          </div>
          {currentTopics.length > 0 && <span className="tag">{currentTopics.length} 个候选</span>}
        </div>
        {currentTopics.length > 0 ? (
          <div className="topic-grid">
            {currentTopics.map((topic) => (
              <TopicRow
                key={topic.id}
                topic={topic}
                selected={selectedTopicId === topic.id}
                onSelect={() => { if (!operationRef.current && selectedTopicId !== topic.id) selectTopic(topic.id); }}
                onDelete={handleDeleteTopic}
                busy={busy}
              />
            ))}
          </div>
        ) : (
          <EmptyBlock title="暂无候选主题" />
        )}
      </section>

      </fieldset>

      {(streaming || streamText) && !script && <section className="content-action-panel" aria-live="polite">
        <h2 className="panel-title">{streaming ? '正在生成脚本' : '未完成的脚本'}</h2>
        <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 280, overflow: 'auto' }}>{streamText || '正在准备…'}</pre>
      </section>}

      <section className="card content-action-panel">
        {script ? (
          <>
            <h2 className="panel-title">脚本已生成</h2>
            <textarea className="input" aria-label="当前脚本正文" rows={8} style={{ width: '100%', resize: 'vertical' }} value={editedContent} disabled={Boolean(busy)} onChange={(e) => setEditedContent(e.target.value)} />
            <div className="row" style={{ flexWrap: 'wrap', marginBlock: 10 }}>
              <button className="btn" disabled={Boolean(busy) || !editedContent.trim() || editedContent === script.content} onClick={() => run('保存脚本', async () => { setScript(await updateScript(script.id, editedContent)); show('success', '脚本已保存'); })}>保存编辑</button>
              <button className="btn btn-ghost" disabled={Boolean(busy) || !editedContent.trim()} onClick={() => handleExport('md')}>导出 Markdown</button>
              <button className="btn btn-ghost" disabled={Boolean(busy) || !editedContent.trim()} onClick={() => handleExport('txt')}>导出纯文本</button>
            </div>
            {editedContent !== script.content ? <p className="muted">保存编辑后继续生成视频。</p> : <Link className="btn action-primary" href={scriptVideoHref(projectId, script.id)}>
              下一步：选择形象并生成视频 <ArrowRight size={16} />
            </Link>}
          </>
        ) : selectedTopic ? (
          <>
            <p className="muted">已选：{selectedTopic.title}</p>
            <button className="btn action-primary" onClick={() => handleGenerateScript(selectedTopic.id)} disabled={streaming || Boolean(busy)}>
              {streaming ? <span className="spin" /> : <FileText size={16} />}
              {streaming ? '正在生成脚本' : '用这个主题生成脚本'}
            </button>
          </>
        ) : (
          <button className="btn action-primary" disabled title="请先选择一个候选主题"><FileText size={16} /> 选择主题后生成脚本</button>
        )}
      </section>

      {(historySources.length > 0 || historyItems.length > 0 || historyTopics.length > 0) && (
        <section className="card history-panel">
          <div className="section-heading">
            <div>
              <h2 className="panel-title">历史记录</h2>
            </div>
            <Clock3 size={18} style={{ color: 'var(--muted)' }} />
          </div>
          <div className="row" role="tablist" aria-label="历史内容" style={{ marginBottom: 12 }}>
            <button className="btn btn-ghost" role="tab" aria-selected={historyTab === 'sources'} onClick={() => setHistoryTab('sources')}>历史抓取</button>
            <button className="btn btn-ghost" role="tab" aria-selected={historyTab === 'topics'} onClick={() => setHistoryTab('topics')}>历史主题</button>
          </div>
          <fieldset disabled={Boolean(busy) || streaming} style={{ border: 0, padding: 0, margin: 0, minWidth: 0, maxHeight: 400, overflow: 'auto' }}>
          {historyTab === 'sources' && historySources.length > 0 && (
            <SourceSection title="历史抓取" sources={historySources} busy={busy} onFetch={handleFetch} onDelete={handleDeleteSource} />
          )}
          {historyTab === 'sources' && historyItems.length > 0 && (
            <div className="history-grid">
              {historyItems.map((item) => (
                <ItemRow key={item.id} item={item} busy={busy} onSummarize={handleSummarize} onTopics={handleTopics} onDelete={handleDeleteItem} compact />
              ))}
            </div>
          )}
          {historyTab === 'topics' && historyTopics.length > 0 && (
            <div className="history-grid">
              {historyTopics.map((topic) => (
                <TopicRow key={topic.id} topic={topic} selected={selectedTopicId === topic.id} onSelect={() => { if (!operationRef.current && selectedTopicId !== topic.id) selectTopic(topic.id); }} onDelete={handleDeleteTopic} busy={busy} compact />
              ))}
            </div>
          )}
          </fieldset>
        </section>
      )}

    </div>
  );
}

function scriptVideoHref(projectId: string, scriptId: string) {
  const href = projectHref('/workspace/video', projectId);
  return `${href}${href.includes('?') ? '&' : '?'}script=${encodeURIComponent(scriptId)}`;
}

function SourceSection({
  title,
  sources,
  busy,
  onFetch,
  onDelete,
}: {
  title: string;
  sources: Source[];
  busy: string;
  onFetch: (id: string) => void;
  onDelete: (source: Source) => void;
}) {
  return (
    <section className="source-section">
      <div className="source-section-title">{title}</div>
      <div className="source-list">
        {sources.map((source) => (
          <div key={source.id} className="source-row">
            <div className="source-row-main">
              <span className="tag">{source.source_type}</span>
              <span className="source-row-text">{source.name || source.url}</span>
            </div>
            <div className="source-row-actions">
              <button className="btn btn-ghost" style={{ padding: '4px 10px' }} onClick={() => onFetch(source.id)} disabled={busy === '自动生成选题'}>
                <Sparkles size={14} /> 重新生成主题
              </button>
              <button className="btn btn-ghost danger-btn" title="删除信息源" style={{ padding: '4px 8px' }} onClick={() => onDelete(source)} disabled={busy === '删除信息源'}>
                <Trash2 size={14} /> 删除
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function EmptyBlock({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="empty-block">
      <div>{title}</div>
      {detail && <p>{detail}</p>}
    </div>
  );
}

function ItemRow({
  item,
  busy,
  onSummarize,
  onTopics,
  onDelete,
  compact = false,
}: {
  item: Item;
  busy: string;
  onSummarize: (id: string) => void;
  onTopics: (id: string) => void;
  onDelete: (item: Item) => void;
  compact?: boolean;
}) {
  return (
    <div className={`content-result-row ${compact ? 'compact' : ''}`}>
      <div>
        <div className="result-title">{item.title || item.original_url}</div>
        {item.summary && <div className="result-summary">{item.summary}</div>}
        <div className="row" style={{ marginTop: 8 }}>
          <span className="tag">{item.status}</span>
          {item.source_name && <span className="tag">{item.source_name}</span>}
        </div>
      </div>
      <div className="result-actions">
        {item.status !== 'summarized' && (
          <button className="btn btn-ghost" onClick={() => onSummarize(item.id)} disabled={busy === '摘要'}>摘要</button>
        )}
        {item.status === 'summarized' && (
          <button className="btn btn-ghost" onClick={() => onTopics(item.id)} disabled={busy === '生成选题'}>
            <Sparkles size={14} /> 重新生成主题
          </button>
        )}
        <button className="btn btn-ghost danger-btn" title="删除条目" onClick={() => onDelete(item)} disabled={busy === '删除条目'}>
          <Trash2 size={14} /> 删除
        </button>
      </div>
    </div>
  );
}

function TopicRow({
  topic,
  selected,
  onSelect,
  onDelete,
  busy,
  compact = false,
}: {
  topic: Topic;
  selected: boolean;
  onSelect: () => void;
  onDelete: (topic: Topic) => void;
  busy: string;
  compact?: boolean;
}) {
  return (
    <div className={`topic-choice ${selected ? 'selected' : ''} ${compact ? 'compact' : ''}`} onClick={onSelect}>
      <div>
        <div className="result-title">{topic.title}</div>
        <div className="result-summary">{topic.angle}</div>
        <div className="row" style={{ marginTop: 8 }}>
          <span className="tag">评分 {topic.score}</span>
          <span className="tag">{topic.risk_level}</span>
        </div>
      </div>
      <div className="result-actions">
        <button className="btn btn-ghost" onClick={(event) => { event.stopPropagation(); onSelect(); }}>
          {selected ? '已选择' : '选择'}
        </button>
        <button className="btn btn-ghost danger-btn" title="删除主题" onClick={(event) => { event.stopPropagation(); onDelete(topic); }} disabled={busy === '删除主题'}>
          <Trash2 size={14} />
        </button>
      </div>
    </div>
  );
}
