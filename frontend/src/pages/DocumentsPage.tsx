import { useState, useEffect } from 'react';
import { Upload, FileText, CheckCircle, Clock, AlertCircle, Loader2, Shield, Search, Filter } from 'lucide-react';
import api, { Document } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import UploadModal from '../components/documents/UploadModal';
import DocumentCard from '../components/documents/DocumentCard';
import { DocumentCardSkeleton, StatsCardSkeleton } from '../components/common/Skeletons';

export default function DocumentsPage() {
  const { isAdmin } = useAuth();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [filter, setFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    loadDocuments();
  }, [filter]);

  const loadDocuments = async () => {
    setLoading(true);
    try {
      const params: any = { limit: 100 };
      if (filter !== 'all') {
        params.status = filter;
      }
      const response = await api.getDocuments(params);
      setDocuments(response.documents);
    } catch (error) {
      console.error('Failed to load documents:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadSuccess = () => {
    setShowUploadModal(false);
    loadDocuments();
  };

  const handleDeleteDocument = async (documentId: string) => {
    if (!isAdmin) {
      alert('Only administrators can delete documents.');
      return;
    }

    if (!confirm('Are you sure you want to delete this document?')) return;

    try {
      await api.deleteDocument(documentId);
      setDocuments(docs => docs.filter(d => d.id !== documentId));
    } catch (error: any) {
      console.error('Failed to delete document:', error);
      alert(error.response?.data?.detail || 'Failed to delete document. You may not have permission.');
    }
  };

  const filteredDocuments = documents.filter(doc => 
    doc.filename.toLowerCase().includes(searchQuery.toLowerCase()) ||
    doc.doc_type.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const stats = {
    total: documents.length,
    completed: documents.filter(d => d.status === 'completed').length,
    processing: documents.filter(d => d.status === 'processing').length,
    failed: documents.filter(d => d.status === 'failed').length,
  };

  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-3 sm:px-6 py-3 sm:py-4 flex-shrink-0">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4 mb-3 sm:mb-4">
          <div className="min-w-0 flex-1">
            <h1 className="text-xl sm:text-2xl font-bold text-gray-900 truncate">Documents</h1>
            <p className="text-xs sm:text-sm text-gray-600 mt-1">
              {isAdmin ? 'Manage all documents' : 'View documents (read-only)'}
            </p>
          </div>
          <button
            data-upload-trigger
            onClick={() => setShowUploadModal(true)}
            className="flex items-center justify-center gap-2 px-3 sm:px-4 py-2.5 bg-gradient-to-r from-primary-500 to-primary-600 text-white rounded-lg hover:from-primary-600 hover:to-primary-700 transition-all shadow-sm text-sm sm:text-base font-medium min-touch-target w-full sm:w-auto"
          >
            <Upload className="w-4 h-4" />
            Upload Document
          </button>
        </div>

        {/* Access Level Badge */}
        {!isAdmin && (
          <div className="mb-3 sm:mb-4 p-2.5 sm:p-3 bg-yellow-50 border border-yellow-200 rounded-lg flex items-start gap-2">
            <Shield className="w-4 h-4 sm:w-5 sm:h-5 text-yellow-600 flex-shrink-0 mt-0.5" />
            <p className="text-xs sm:text-sm text-yellow-800 leading-relaxed">
              You have read-only access. Contact an administrator to delete or modify documents.
            </p>
          </div>
        )}

        {/* Stats Grid - Responsive */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 sm:gap-4 mb-3 sm:mb-4">
          <div className="bg-gray-50 rounded-lg p-2.5 sm:p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs sm:text-sm text-gray-600">Total</span>
              <FileText className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-gray-400" />
            </div>
            <p className="text-xl sm:text-2xl font-bold text-gray-900">{stats.total}</p>
          </div>
          <div className="bg-green-50 rounded-lg p-2.5 sm:p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs sm:text-sm text-green-600">Completed</span>
              <CheckCircle className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-green-500" />
            </div>
            <p className="text-xl sm:text-2xl font-bold text-green-700">{stats.completed}</p>
          </div>
          <div className="bg-yellow-50 rounded-lg p-2.5 sm:p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs sm:text-sm text-yellow-600">Processing</span>
              <Clock className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-yellow-500" />
            </div>
            <p className="text-xl sm:text-2xl font-bold text-yellow-700">{stats.processing}</p>
          </div>
          <div className="bg-red-50 rounded-lg p-2.5 sm:p-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs sm:text-sm text-red-600">Failed</span>
              <AlertCircle className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-red-500" />
            </div>
            <p className="text-xl sm:text-2xl font-bold text-red-700">{stats.failed}</p>
          </div>
        </div>

        {/* Search & Filters - Mobile Optimized */}
        <div className="space-y-2 sm:space-y-0 sm:flex sm:items-center sm:gap-4">
          {/* Search Bar */}
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            <input
              type="text"
              placeholder="Search documents..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm sm:text-base"
            />
          </div>

          {/* Mobile Filter Toggle */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            className="sm:hidden flex items-center justify-center gap-2 w-full px-4 py-2.5 border border-gray-300 rounded-lg bg-white hover:bg-gray-50 transition-colors min-touch-target"
          >
            <Filter className="w-4 h-4 text-gray-600" />
            <span className="text-sm font-medium text-gray-700">
              Filters {filter !== 'all' && `(${filter})`}
            </span>
          </button>

          {/* Desktop Filter Dropdown */}
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="hidden sm:block px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent bg-white text-sm sm:text-base min-w-[140px]"
          >
            <option value="all">All Status</option>
            <option value="completed">Completed</option>
            <option value="processing">Processing</option>
            <option value="failed">Failed</option>
          </select>
        </div>

        {/* Mobile Filter Dropdown */}
        {showFilters && (
          <div className="sm:hidden mt-2 p-2 bg-gray-50 border border-gray-200 rounded-lg animate-slideUp">
            <p className="text-xs font-medium text-gray-600 mb-2 px-2">Filter by status:</p>
            <div className="space-y-1">
              {['all', 'completed', 'processing', 'failed'].map((status) => (
                <button
                  key={status}
                  onClick={() => {
                    setFilter(status);
                    setShowFilters(false);
                  }}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors min-touch-target ${
                    filter === status
                      ? 'bg-primary-100 text-primary-700 font-medium'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`}
                >
                  {status === 'all' ? 'All Status' : status.charAt(0).toUpperCase() + status.slice(1)}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Documents List */}
      <div className="flex-1 overflow-y-auto p-3 sm:p-6 scroll-smooth-touch">
        {loading ? (
          <div className="p-3 sm:p-6">
            {/* Stats Skeletons */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 mb-6">
              <StatsCardSkeleton />
              <StatsCardSkeleton />
              <StatsCardSkeleton />
              <StatsCardSkeleton />
            </div>

            {/* Document Cards Skeletons */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 sm:gap-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <DocumentCardSkeleton key={i} />
              ))}
            </div>
          </div>
          
        ) : filteredDocuments.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center px-4">
            <FileText className="w-12 h-12 sm:w-16 sm:h-16 text-gray-300 mb-4" />
            <h3 className="text-base sm:text-lg font-medium text-gray-900 mb-2">
              {searchQuery ? 'No documents found' : 'No documents yet'}
            </h3>
            <p className="text-sm sm:text-base text-gray-600 mb-4">
              {searchQuery
                ? 'Try adjusting your search query'
                : 'Upload your first document to get started'}
            </p>
            {!searchQuery && (
              <button
                data-upload-trigger
                onClick={() => setShowUploadModal(true)}
                className="flex items-center justify-center gap-2 px-3 sm:px-4 py-2.5 bg-gradient-to-r from-primary-500 to-primary-600 text-white rounded-lg hover:from-primary-600 hover:to-primary-700 transition-all shadow-sm text-sm sm:text-base font-medium min-touch-target w-full sm:w-auto"
              >
                <Upload className="w-4 h-4" />
                Upload Document
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 sm:gap-4">
            {filteredDocuments.map((doc) => (
              <DocumentCard
                key={doc.id}
                document={doc}
                onDelete={handleDeleteDocument}
                onRefresh={loadDocuments}
                canDelete={isAdmin}
              />
            ))}
          </div>
        )}
      </div>

      {/* Upload Modal */}
      {showUploadModal && (
        <UploadModal
          onClose={() => setShowUploadModal(false)}
          onSuccess={handleUploadSuccess}
        />
      )}
    </div>
  );
}