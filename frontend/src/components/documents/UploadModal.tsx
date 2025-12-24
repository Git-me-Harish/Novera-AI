import { useState } from 'react';
import { X, Upload, File, Loader2, CheckCircle } from 'lucide-react';
import api from '../../services/api';

interface UploadModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

export default function UploadModal({ onClose, onSuccess }: UploadModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState('finance');
  const [department, setDepartment] = useState('');
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      
      // Validate file size (50MB max)
      if (selectedFile.size > 50 * 1024 * 1024) {
        setError('File size must be less than 50MB');
        return;
      }

      // Validate file type
      const allowedTypes = ['.pdf', '.docx', '.doc', '.txt', '.xlsx', '.xls'];
      const fileExt = selectedFile.name.substring(selectedFile.name.lastIndexOf('.')).toLowerCase();
      
      if (!allowedTypes.includes(fileExt)) {
        setError(`File type ${fileExt} not supported. Allowed: ${allowedTypes.join(', ')}`);
        return;
      }

      setFile(selectedFile);
      setError(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    setError(null);
    setProgress(0);

    try {
      const progressInterval = setInterval(() => {
        setProgress(prev => Math.min(prev + 10, 90));
      }, 200);

      await api.uploadDocument(file, docType, department || undefined);

      clearInterval(progressInterval);
      setProgress(100);
      setSuccess(true);

      setTimeout(() => {
        onSuccess();
      }, 1500);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Upload failed. Please try again.');
      setProgress(0);
    } finally {
      setUploading(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const droppedFile = e.dataTransfer.files[0];
      const mockEvent = {
        target: { files: [droppedFile] }
      } as any;
      handleFileChange(mockEvent);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-3 sm:px-4 pt-4 pb-20 text-center sm:p-0">
        {/* Overlay */}
        <div
          className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"
          onClick={onClose}
        />

        {/* Modal */}
        <div className="relative inline-block align-bottom bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-lg w-full mx-3 sm:mx-0">
          {/* Header */}
          <div className="flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 border-b border-gray-200">
            <h3 className="text-base sm:text-lg font-semibold text-gray-900">Upload Document</h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-500 transition-colors p-2 -mr-2 min-touch-target"
              disabled={uploading}
              aria-label="Close"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Body */}
          <div className="px-4 sm:px-6 py-4 space-y-4">
            {/* File Upload Area */}
            <div
              onDragOver={handleDragOver}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-lg p-4 sm:p-8 text-center transition-colors ${
                file
                  ? 'border-primary-300 bg-primary-50'
                  : 'border-gray-300 hover:border-primary-400 bg-gray-50'
              }`}
            >
              {file ? (
                <div className="flex items-center justify-center gap-3">
                  <File className="w-6 h-6 sm:w-8 sm:h-8 text-primary-600 flex-shrink-0" />
                  <div className="text-left flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{file.name}</p>
                    <p className="text-xs text-gray-500">
                      {(file.size / 1024 / 1024).toFixed(2)} MB
                    </p>
                  </div>
                  {!uploading && (
                    <button
                      onClick={() => setFile(null)}
                      className="text-gray-400 hover:text-red-600 transition-colors p-2 -mr-2 flex-shrink-0 min-touch-target"
                      aria-label="Remove file"
                    >
                      <X className="w-5 h-5" />
                    </button>
                  )}
                </div>
              ) : (
                <>
                  <Upload className="w-8 h-8 sm:w-12 sm:h-12 text-gray-400 mx-auto mb-2 sm:mb-3" />
                  <p className="text-sm text-gray-600 mb-2">
                    <span className="hidden sm:inline">Drag and drop your file here, or </span>
                    <span className="sm:hidden">Tap to upload or </span>
                  </p>
                  <label className="inline-flex items-center px-3 sm:px-4 py-2 bg-white border border-gray-300 rounded-lg text-xs sm:text-sm font-medium text-gray-700 hover:bg-gray-50 cursor-pointer transition-colors min-touch-target">
                    Browse Files
                    <input
                      type="file"
                      onChange={handleFileChange}
                      accept=".pdf,.docx,.doc,.txt,.xlsx,.xls"
                      className="sr-only"
                      disabled={uploading}
                    />
                  </label>
                  <p className="text-xs text-gray-500 mt-2">
                    PDF, DOCX, TXT, XLSX (Max 50MB)
                  </p>
                </>
              )}
            </div>

            {/* Progress Bar */}
            {uploading && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs sm:text-sm">
                  <span className="text-gray-600">Uploading...</span>
                  <span className="text-gray-900 font-medium">{progress}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-gradient-to-r from-primary-500 to-primary-600 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            )}

            {/* Success Message */}
            {success && (
              <div className="flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded-lg">
                <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
                <p className="text-xs sm:text-sm text-green-800">Document uploaded successfully!</p>
              </div>
            )}

            {/* Error Message */}
            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-xs sm:text-sm text-red-800 break-words">{error}</p>
              </div>
            )}

            {/* Form Fields */}
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Document Type *
                </label>
                <select
                  value={docType}
                  onChange={(e) => setDocType(e.target.value)}
                  disabled={uploading}
                  className="w-full px-3 sm:px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm sm:text-base"
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
                  disabled={uploading}
                  className="w-full px-3 sm:px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm sm:text-base"
                />
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="px-4 sm:px-6 py-3 sm:py-4 bg-gray-50 border-t border-gray-200 flex flex-col-reverse sm:flex-row sm:items-center sm:justify-end gap-2 sm:gap-3">
            <button
              onClick={onClose}
              disabled={uploading}
              className="w-full sm:w-auto px-4 py-2.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors min-touch-target"
            >
              Cancel
            </button>
            <button
              onClick={handleUpload}
              disabled={!file || uploading || success}
              className="w-full sm:w-auto px-4 py-2.5 text-sm font-medium text-white bg-gradient-to-r from-primary-500 to-primary-600 rounded-lg hover:from-primary-600 hover:to-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-sm min-touch-target"
            >
              {uploading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 inline-block animate-spin" />
                  Uploading...
                </>
              ) : success ? (
                <>
                  <CheckCircle className="w-4 h-4 mr-2 inline-block" />
                  Uploaded
                </>
              ) : (
                <>
                  <Upload className="w-4 h-4 mr-2 inline-block" />
                  Upload
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}