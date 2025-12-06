import { useState, useEffect } from 'react';
import { Save, X, RotateCcw, Trash2, History, Loader2 } from 'lucide-react';
import { ChunkData } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';

interface ChunkEditorProps {
  chunk: ChunkData;
  onSave: (chunkId: string, newContent: string) => Promise<void>;
  onRevert: (chunkId: string) => Promise<void>;
  onDelete: (chunkId: string) => Promise<void>;
  onViewHistory: (chunkId: string) => void;
  onClose: () => void;
}

export default function ChunkEditor({
  chunk,
  onSave,
  onRevert,
  onDelete,
  onViewHistory,
  onClose
}: ChunkEditorProps) {
  const { isAdmin } = useAuth();
  const [content, setContent] = useState(chunk.content);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    setHasChanges(content.trim() !== chunk.content.trim());
  }, [content, chunk.content]);

  const handleSave = async () => {
    if (!hasChanges || content.trim().length < 10) return;

    setSaving(true);
    try {
      await onSave(chunk.id, content.trim());
      onClose();
    } catch (error) {
      console.error('Failed to save chunk:', error);
    } finally {
      setSaving(false);
    }
  };

  const handleRevert = async () => {
    if (!confirm('Are you sure you want to revert this chunk to its original content?')) return;

    try {
      await onRevert(chunk.id);
      onClose();
    } catch (error) {
      console.error('Failed to revert chunk:', error);
    }
  };

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this chunk? This action cannot be undone.')) return;

    try {
      await onDelete(chunk.id);
      onClose();
    } catch (error) {
      console.error('Failed to delete chunk:', error);
    }
  };

  const charCount = content.length;
  const charLimit = 10000;
  const isOverLimit = charCount > charLimit;
  const isTooShort = content.trim().length < 10;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black bg-opacity-50">
      <div className="flex items-center justify-center min-h-screen px-4 py-8">
        <div className="relative bg-white rounded-lg shadow-xl w-full max-w-4xl">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <div>
              <h3 className="text-lg font-semibold text-gray-900">
                Edit Chunk #{chunk.chunk_index + 1}
              </h3>
              <p className="text-sm text-gray-600 mt-1">
                Type: {chunk.chunk_type} | Pages: {chunk.page_numbers.join(', ')}
                {chunk.section_title && ` | Section: ${chunk.section_title}`}
              </p>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Edit Status */}
          {chunk.is_edited && (
            <div className="px-6 py-3 bg-yellow-50 border-b border-yellow-200">
              <p className="text-sm text-yellow-800">
                This chunk has been edited {chunk.edit_count} time{chunk.edit_count !== 1 ? 's' : ''}
                {chunk.edited_at && ` - Last edited: ${new Date(chunk.edited_at).toLocaleString()}`}
              </p>
            </div>
          )}

          {/* Admin Warning for Regular Users */}
          {!isAdmin && (
            <div className="px-6 py-3 bg-blue-50 border-b border-blue-200">
              <p className="text-sm text-blue-800">
                You are viewing this chunk in read-only mode. Contact an administrator to make changes.
              </p>
            </div>
          )}

          {/* Content Editor */}
          <div className="px-6 py-4">
            <div className="mb-2 flex items-center justify-between">
              <label className="block text-sm font-medium text-gray-700">
                Chunk Content
              </label>
              <span className={`text-sm ${isOverLimit ? 'text-red-600' : isTooShort ? 'text-yellow-600' : 'text-gray-500'}`}>
                {charCount} / {charLimit} characters
                {isTooShort && ' (minimum 10 characters)'}
              </span>
            </div>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              disabled={!isAdmin || saving}
              rows={20}
              className={`w-full px-4 py-3 border rounded-lg font-mono text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent resize-none ${
                isOverLimit ? 'border-red-300' : 'border-gray-300'
              } ${!isAdmin ? 'bg-gray-50 cursor-not-allowed' : ''}`}
              placeholder="Enter chunk content..."
            />
            {isOverLimit && (
              <p className="mt-2 text-sm text-red-600">
                Content exceeds maximum length of {charLimit} characters
              </p>
            )}
          </div>

          {/* Metadata */}
          <div className="px-6 py-4 bg-gray-50 border-t border-gray-200">
            <h4 className="text-sm font-medium text-gray-700 mb-2">Metadata</h4>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-gray-600">Token Count:</span>
                <span className="ml-2 font-medium text-gray-900">{chunk.token_count}</span>
              </div>
              <div>
                <span className="text-gray-600">Edit Count:</span>
                <span className="ml-2 font-medium text-gray-900">{chunk.edit_count}</span>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              {isAdmin && chunk.is_edited && (
                <button
                  onClick={handleRevert}
                  className="flex items-center px-3 py-2 text-sm font-medium text-yellow-700 bg-yellow-100 rounded-lg hover:bg-yellow-200 transition-colors"
                  disabled={saving}
                >
                  <RotateCcw className="w-4 h-4 mr-2" />
                  Revert to Original
                </button>
              )}
              {chunk.edit_count > 0 && (
                <button
                  onClick={() => onViewHistory(chunk.id)}
                  className="flex items-center px-3 py-2 text-sm font-medium text-gray-700 bg-gray-200 rounded-lg hover:bg-gray-300 transition-colors"
                >
                  <History className="w-4 h-4 mr-2" />
                  View History ({chunk.edit_count})
                </button>
              )}
              {isAdmin && (
                <button
                  onClick={handleDelete}
                  className="flex items-center px-3 py-2 text-sm font-medium text-red-700 bg-red-100 rounded-lg hover:bg-red-200 transition-colors"
                  disabled={saving}
                >
                  <Trash2 className="w-4 h-4 mr-2" />
                  Delete Chunk
                </button>
              )}
            </div>

            <div className="flex items-center space-x-3">
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                disabled={saving}
              >
                Cancel
              </button>
              {isAdmin && (
                <button
                  onClick={handleSave}
                  disabled={!hasChanges || saving || isOverLimit || isTooShort}
                  className="flex items-center px-4 py-2 text-sm font-medium text-white bg-primary-600 rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {saving ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save className="w-4 h-4 mr-2" />
                      Save Changes
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}