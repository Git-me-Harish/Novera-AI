import { useState } from 'react';
import { Save, X, Loader2 } from 'lucide-react';
import { DocumentInfo } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';

interface DocumentMetadataEditorProps {
  docInfo: DocumentInfo;
  onSave: (metadata: any) => Promise<void>;
  onClose: () => void;
}

export default function DocumentMetadataEditor({
  docInfo,
  onSave,
  onClose
}: DocumentMetadataEditorProps) {
  const { isAdmin } = useAuth();
  const [docType, setDocType] = useState(docInfo.doc_type);
  const [department, setDepartment] = useState(docInfo.department || '');
  const [saving, setSaving] = useState(false);

  const hasChanges = docType !== docInfo.doc_type || department !== (docInfo.department || '');

  const handleSave = async () => {
    if (!hasChanges) return;

    setSaving(true);
    try {
      await onSave({ doc_type: docType, department: department || null });
      onClose();
    } catch (error) {
      console.error('Failed to save metadata:', error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black bg-opacity-50">
      <div className="flex items-center justify-center min-h-screen px-4">
        <div className="relative bg-white rounded-lg shadow-xl w-full max-w-md">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">Edit Document Metadata</h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Admin Warning */}
          {!isAdmin && (
            <div className="px-6 py-3 bg-blue-50 border-b border-blue-200">
              <p className="text-sm text-blue-800">
                Read-only mode. Contact an administrator to make changes.
              </p>
            </div>
          )}

          {/* Form */}
          <div className="px-6 py-4 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Document Type
              </label>
              <select
                value={docType}
                onChange={(e) => setDocType(e.target.value)}
                disabled={!isAdmin || saving}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:bg-gray-50 disabled:cursor-not-allowed"
              >
                <option value="finance">Finance</option>
                <option value="hrms">HRMS</option>
                <option value="policy">Policy</option>
                <option value="other">Other</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Department (Optional)
              </label>
              <input
                type="text"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                placeholder="e.g., Finance, HR, Operations"
                disabled={!isAdmin || saving}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:bg-gray-50 disabled:cursor-not-allowed"
              />
            </div>

            {/* Read-only Info */}
            <div className="pt-4 border-t border-gray-200 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-600">File Size:</span>
                <span className="font-medium text-gray-900">{docInfo.file_size_mb} MB</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Total Pages:</span>
                <span className="font-medium text-gray-900">{docInfo.total_pages}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Total Chunks:</span>
                <span className="font-medium text-gray-900">{docInfo.total_chunks}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Status:</span>
                <span className="font-medium text-gray-900 capitalize">{docInfo.status}</span>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 flex items-center justify-end space-x-3">
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
                disabled={!hasChanges || saving}
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
  );
}