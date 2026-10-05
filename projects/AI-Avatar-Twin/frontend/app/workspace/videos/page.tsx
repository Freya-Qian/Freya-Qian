'use client';

import { useEffect, useState } from 'react';
import { Download, Film, Package, RefreshCw, Trash2 } from 'lucide-react';
import { listVideos, retryVideo, fetchBlob, download, deleteVideo, Video } from '@/lib/api/client';
import { BackStep } from '@/components/back-step';
import { getProjectFromUrl, getRememberedProject, projectHref } from '@/lib/project-url';

export default function VideosPage() {
  const [videos, setVideos] = useState<Video[]>([]);
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);
  const projectId = getProjectFromUrl() || getRememberedProject();

  async function refresh() {
    setLoading(true);
    try {
      setVideos(await listVideos());
    } catch (e) {
      setErr(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const kickoff = setTimeout(refresh, 0);
    // 自动轮询：有生成中的视频时每 4 秒刷新，无需人工刷新
    const timer = setInterval(refresh, 4000);
    return () => {
      clearTimeout(kickoff);
      clearInterval(timer);
    };
  }, []);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="title">我的视频</h1>
          <p className="subtitle">预览成片，下载 MP4 或打包素材。</p>
        </div>
        <div className="page-actions">
          <BackStep fallbackHref={projectHref('/workspace/video', projectId)} />
          <button className="btn btn-ghost" onClick={refresh} disabled={loading}>
            <RefreshCw size={16} /> 刷新
          </button>
        </div>
      </div>

      {err && <div className="err" style={{ marginBottom: 16 }}>{err}</div>}

      {videos.length === 0 && !loading && <div className="muted">暂无视频</div>}

      {videos.map((v) => (
        <VideoCard key={v.id} v={v} onRefresh={refresh} />
      ))}
    </div>
  );
}

function VideoCard({ v, onRefresh }: { v: Video; onRefresh: () => void }) {
  const [src, setSrc] = useState('');
  const [err, setErr] = useState('');

  useEffect(() => {
    let alive = true;
    let objectUrl = '';
    if (v.status === 'success') {
      fetchBlob(`/videos/${v.id}/file`).then((url) => {
        if (!alive) {
          URL.revokeObjectURL(url);
          return;
        }
        objectUrl = url;
        setSrc(url);
      }).catch(() => {});
    }
    return () => {
      alive = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [v.id, v.status]);

  const handleDelete = async () => {
    if (!window.confirm(`确认删除视频任务「${v.id.slice(-6)}」？MP4、封面、字幕和素材包也会一起删除。`)) return;
    try {
      await deleteVideo(v.id);
      onRefresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : '删除失败');
    }
  };

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Film size={18} style={{ color: 'var(--primary)' }} />
          <b>视频 {v.id.slice(-6)}</b>
          <StatusTag status={v.status} />
        </div>
        <button className="btn btn-ghost danger-btn" title="删除视频" style={{ padding: '4px 8px' }} onClick={handleDelete}>
          <Trash2 size={14} /> 删除
        </button>
      </div>
      {err && <div className="err" style={{ marginTop: 8 }}>{err}</div>}
      {v.status === 'success' && src && (
        <video controls playsInline style={{ width: '100%', maxWidth: 360, marginTop: 10, borderRadius: 8, background: '#05070a' }} src={src} />
      )}
      {v.status === 'success' && v.error_message && (
        <div className="err" style={{ marginTop: 8 }}>{v.error_message}</div>
      )}
      {v.status === 'failed' && (
        <div style={{ marginTop: 8 }}>
          <div className="err">{v.error_message || '生成失败'}</div>
          <button className="btn btn-ghost" style={{ marginTop: 8 }} onClick={() => retryVideo(v.id).then(onRefresh).catch((e) => setErr(e.message))}>
            重试
          </button>
        </div>
      )}
      {v.status === 'success' && (
        <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
          <button className="btn btn-ghost" onClick={() => download(`/videos/${v.id}/file`, 'video.mp4')}><Download size={16} /> 下载 MP4</button>
          <button className="btn btn-ghost" onClick={() => download(`/videos/${v.id}/export`, '素材包.zip')}><Package size={16} /> 下载素材包</button>
        </div>
      )}
    </div>
  );
}

function StatusTag({ status }: { status: string }) {
  const map: Record<string, { text: string; color: string }> = {
    success: { text: '成功', color: 'var(--success)' },
    failed: { text: '失败', color: 'var(--danger)' },
    rendering: { text: '生成中', color: 'var(--primary)' },
    queued: { text: '排队中', color: 'var(--primary)' },
  };
  const s = map[status] || { text: status, color: 'var(--muted)' };
  return <span className={`tag${status === 'rendering' || status === 'queued' ? ' status-progress' : ''}`} style={{ color: s.color }}>{s.text}</span>;
}
