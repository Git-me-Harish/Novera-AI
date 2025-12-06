import { useState, useEffect } from 'react';
import { X, Clock, User, Loader2, ChevronDown, ChevronUp } from 'lucide-react';
import api, { EditHistoryItem } from '../../services/api';

interface EditHistoryModalProps {
  chunkId: string;
  onClose: () => void;
}

export default function EditHistoryModal({ chunkId, onClose }: EditHistoryModalProps) {
  const [history, setHistory] = useState<EditHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    loadHistory();
  }, [chunkId]);

  const loadHistory = async () => {
    setLoading(true);
    try {
      const data = await api.getChunkHistory(chunkId, 20);
      setHistory(data);
    } catch (error) {
      console.error('Failed to load edit history:', error);
    } finally {
      setLoading(false);
    }
  };

  const toggleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id);
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black bg-opacity-50">
      <div className="flex items-center justify-center min-h-screen px-4 py-8">
        <div className="relative bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">Edit History</h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-6">
            {loading ? (
              <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 text-primary-500 animate-spin" />
              </div>
            ) : history.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-64 text-center">
                <Clock className="w-16 h-16 text-gray-300 mb-4" />
                <p className="text-gray-600">No edit history available</p>
              </div>
            ) : (
              <div className="space-y-4">
                {history.map((item) => (
                  <div
                    key={item.id}
                    className="bg-white border border-gray-200 rounded-lg overflow-hidden"
                  >
                    {/* History Item Header */}
                    <div className="p-4 bg-gray-50 border-b border-gray-200">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                          <User className="w-4 h-4 text-gray-400" />
                          <div>
                            <p className="text-sm font-medium text-gray-900">
                              Editor ID: {item.edited_by}
                            </p>
                            <div className="flex items-center space-x-2 text-xs text-gray-500 mt-1">
                              <Clock className="w-3 h-3" />
                              <span>{new Date(item.edited_at).toLocaleString()}</span>
                            </div>
                          </div>
                        </div>
                        {item.change_summary && (
                          <span className="text-sm text-gray-600 italic">
                            {item.change_summary}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Content Comparison */}
                    <div className="p-4">
                      <button
                        onClick={() => toggleExpand(item.id)}
                        className="flex items-center justify-between w-full text-sm font-medium text-gray-700 hover:text-gray-900 transition-colors"
                      >
                        <span>View Changes</span>
                        {expandedId === item.id ? (
                          <ChevronUp className="w-4 h-4" />
                        ) : (
                          <ChevronDown className="w-4 h-4" />
                        )}
                      </button>

                      {expandedId === item.id && (
                        <div className="mt-4 grid grid-cols-2 gap-4">
                          {/* Old Content */}
                          <div>
                            <h4 className="text-xs font-semibold text-red-600 mb-2">
                              OLD CONTENT
                            </h4>
                            <div className="bg-red-50 border border-red-200 rounded-lg p-3 max-h-64 overflow-y-auto">
                              <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono">
                                {item.old_content}
                              </pre>
                            </div>
                          </div>

                          {/* New Content */}
                          <div>
                            <h4 className="text-xs font-semibold text-green-600 mb-2">
                              NEW CONTENT
                            </h4>
                            <div className="bg-green-50 border border-green-200 rounded-lg p-3 max-h-64 overflow-y-auto">
                              <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono">
                                {item.new_content}
                              </pre>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 flex items-center justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}