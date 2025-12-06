import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  FileText,
  Edit,
  Eye,
  BarChart3,
  Loader2,
  AlertCircle,
  Info
} from 'lucide-react';
import api, { DocumentInfo, ChunkData, DocumentEditStats } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { toast } from '../utils/toast';
import DocumentViewer from '../components/documents/DocumentViewer';
import ChunkList from '../components/documents/ChunkList';
import ChunkEditor from '../components/documents/ChunkEditor';
import EditHistoryModal from '../components/documents/EditHistoryModal';
import DocumentMetadataEditor from '../components/documents/DocumentMetadataEditor';

export default function DocumentEditorPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const navigate = useNavigate();
  const { isAdmin } = useAuth();

  const [docInfo, setDocInfo] = useState<DocumentInfo | null>(null);
  const [chunks, setChunks] = useState<ChunkData[]>([]);
  const [stats, setStats] = useState<DocumentEditStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showDocViewer, setShowDocViewer] = useState(false);
  const [showMetadataEditor, setShowMetadataEditor] = useState(false);
  const [selectedChunk, setSelectedChunk] = useState<ChunkData | null>(null);
  const [historyChunkId, setHistoryChunkId] = useState<string | null>(null);

  useEffect(() => {
    if (documentId) {
      loadDocument();
    }
  }, [documentId]);

  const loadDocument = async () => {
    if (!documentId) return;

    setLoading(true);
    setError(null);

    try {
      const [info, chunksData, statsData] = await Promise.all([
        api.getDocumentInfo(documentId),
        api.getDocumentChunks(documentId),
        api.getDocumentEditStats(documentId)
      ]);

      setDocInfo(info);
      setChunks(chunksData);
      setStats(statsData);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load document');
      toast.error('Failed to load document');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveChunk = async (chunkId: string, newContent: string) => {
    try {
      const updatedChunk = await api.editChunk(chunkId, newContent);
      
      setChunks(prev => prev.map(c => c.id === chunkId ? updatedChunk : c));
      
      loadDocument();
      
      toast.success('Chunk updated successfully. Embedding regenerated.');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to save chunk');
      throw err;
    }
  };

  const handleRevertChunk = async (chunkId: string) => {
    try {
      await api.revertChunk(chunkId);
      
      loadDocument();
      
      toast.success('Chunk reverted to original content');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to revert chunk');
      throw err;
    }
  };

  const handleDeleteChunk = async (chunkId: string) => {
    try {
      await api.deleteChunk(chunkId);
      
      setChunks(prev => prev.filter(c => c.id !== chunkId));
      
      loadDocument();
      
      toast.success('Chunk deleted successfully');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to delete chunk');
      throw err;
    }
  };

  const handleSaveMetadata = async (metadata: any) => {
    toast.info('Metadata update feature coming soon');
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-primary-500 animate-spin" />
      </div>
    );
  }

  if (error || !docInfo) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center px-4">
        <AlertCircle className="w-16 h-16 text-red-400 mb-4" />
        <h2 className="text-xl font-semibold text-gray-900 mb-2">Failed to Load Document</h2>
        <p className="text-gray-600 mb-6">{error}</p>
        <button
          onClick={() => navigate('/documents')}
          className="flex items-center px-4 py-2 text-white bg-primary-600 rounded-lg hover:bg-primary-700 transition-colors"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Documents
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-4">
            <button
              onClick={() => navigate('/documents')}
              className="text-gray-600 hover:text-gray-900 transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                {docInfo.original_filename}
              </h1>
              <p className="text-sm text-gray-600 mt-1">
                {docInfo.doc_type} {docInfo.department && `| ${docInfo.department}`} | 
                {docInfo.file_size_mb} MB | {docInfo.total_pages} pages
              </p>
            </div>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => setShowDocViewer(true)}
              className="flex items-center px-3 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
            >
              <Eye className="w-4 h-4 mr-2" />
              Preview
            </button>
            <button
              onClick={() => setShowMetadataEditor(true)}
              className="flex items-center px-3 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
            >
              <Edit className="w-4 h-4 mr-2" />
              Metadata
            </button>
          </div>
        </div>

        {/* Access Level Info */}
        {!isAdmin && (
          <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg flex items-center gap-2">
            <Info className="w-5 h-5 text-yellow-600" />
            <p className="text-sm text-yellow-800">
              You are viewing this document in read-only mode. Contact an administrator to make edits.
            </p>
          </div>
        )}

        {/* Statistics */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="bg-gray-50 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-gray-600">Total Chunks</span>
                <FileText className="w-4 h-4 text-gray-400" />
              </div>
              <p className="text-xl font-bold text-gray-900">{stats.total_chunks}</p>
            </div>

            <div className="bg-green-50 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-green-600">Edited</span>
                <BarChart3 className="w-4 h-4 text-green-500" />
              </div>
              <p className="text-xl font-bold text-green-700">{stats.edited_chunks}</p>
            </div>

            <div className="bg-blue-50 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-blue-600">Original</span>
                <FileText className="w-4 h-4 text-blue-500" />
              </div>
              <p className="text-xl font-bold text-blue-700">{stats.unedited_chunks}</p>
            </div>

            <div className="bg-purple-50 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-purple-600">Total Edits</span>
                <Edit className="w-4 h-4 text-purple-500" />
              </div>
              <p className="text-xl font-bold text-purple-700">{stats.total_edits}</p>
            </div>

            <div className="bg-yellow-50 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-yellow-600">Edited %</span>
                <BarChart3 className="w-4 h-4 text-yellow-500" />
              </div>
              <p className="text-xl font-bold text-yellow-700">{stats.edit_percentage}%</p>
            </div>
          </div>
        )}
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-hidden">
        <ChunkList
          chunks={chunks}
          onEditChunk={(chunk) => setSelectedChunk(chunk)}
        />
      </div>

      {/* Modals */}
      {showDocViewer && documentId && (
        <DocumentViewer
          documentId={documentId}
          onClose={() => setShowDocViewer(false)}
        />
      )}

      {showMetadataEditor && (
        <DocumentMetadataEditor
          docInfo={docInfo}
          onSave={handleSaveMetadata}
          onClose={() => setShowMetadataEditor(false)}
        />
      )}

      {selectedChunk && (
        <ChunkEditor
          chunk={selectedChunk}
          onSave={handleSaveChunk}
          onRevert={handleRevertChunk}
          onDelete={handleDeleteChunk}
          onViewHistory={(chunkId) => {
            setHistoryChunkId(chunkId);
            setSelectedChunk(null);
          }}
          onClose={() => setSelectedChunk(null)}
        />
      )}

      {historyChunkId && (
        <EditHistoryModal
          chunkId={historyChunkId}
          onClose={() => setHistoryChunkId(null)}
        />
      )}
    </div>
  );
}