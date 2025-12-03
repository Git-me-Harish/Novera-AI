import { FileText, Calendar, Trash2, CheckCircle, Clock, AlertCircle, Eye } from 'lucide-react';
import { Document } from '../../services/api';

interface DocumentCardProps {
  document: Document;
  onDelete: (id: string) => void;
  onRefresh: () => void;
  canDelete?: boolean;
}

export default function DocumentCard({ document, onDelete, canDelete = false }: DocumentCardProps) {
  const getStatusIcon = () => {
    switch (document.status) {
      case 'completed':
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'processing':
        return <Clock className="w-5 h-5 text-yellow-500 animate-spin" />;
      case 'failed':
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      default:
        return <FileText className="w-5 h-5 text-gray-400" />;
    }
  };

  const getStatusColor = () => {
    switch (document.status) {
      case 'completed':
        return 'bg-green-100 text-green-800';
      case 'processing':
        return 'bg-yellow-100 text-yellow-800';
      case 'failed':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 hover:shadow-md transition-shadow">
      <div className="p-4">
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center space-x-2 flex-1">
            {getStatusIcon()}
            <h3 className="font-medium text-gray-900 truncate" title={document.filename}>
              {document.filename}
            </h3>
          </div>
        </div>

        {/* Status Badge */}
        <div className="mb-3">
          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor()}`}>
            {document.status}
          </span>
        </div>

        {/* Metadata */}
        <div className="space-y-2 text-sm text-gray-600">
          <div className="flex items-center justify-between">
            <span>Type:</span>
            <span className="font-medium text-gray-900">{document.doc_type}</span>
          </div>
          {document.department && (
            <div className="flex items-center justify-between">
              <span>Department:</span>
              <span className="font-medium text-gray-900">{document.department}</span>
            </div>
          )}
          <div className="flex items-center justify-between">
            <span>Pages:</span>
            <span className="font-medium text-gray-900">{document.total_pages}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Chunks:</span>
            <span className="font-medium text-gray-900">{document.total_chunks}</span>
          </div>
          <div className="flex items-center space-x-1 text-xs text-gray-500">
            <Calendar className="w-3 h-3" />
            <span>{new Date(document.upload_date).toLocaleDateString()}</span>
          </div>
        </div>

        {/* Actions */}
        <div className="mt-4 pt-4 border-t border-gray-200 flex items-center justify-between">
          <button
            className="flex items-center text-sm text-gray-600 hover:text-gray-900"
            title="View details"
          >
            <Eye className="w-4 h-4 mr-1" />
            View
          </button>
          
          {canDelete ? (
            <button
              onClick={() => onDelete(document.id)}
              className="flex items-center text-sm text-red-600 hover:text-red-700"
              title="Delete document"
            >
              <Trash2 className="w-4 h-4 mr-1" />
              Delete
            </button>
          ) : (
            <span className="text-xs text-gray-400">Read-only</span>
          )}
        </div>
      </div>
    </div>
  );
}