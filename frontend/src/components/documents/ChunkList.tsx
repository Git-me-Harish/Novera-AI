import { useState } from 'react';
import { Edit, FileText, CheckCircle, Search } from 'lucide-react';
import { ChunkData } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';

interface ChunkListProps {
  chunks: ChunkData[];
  onEditChunk: (chunk: ChunkData) => void;
}

export default function ChunkList({ chunks, onEditChunk }: ChunkListProps) {
  const { isAdmin } = useAuth();
  const [searchQuery, setSearchQuery] = useState('');
  const [filterEdited, setFilterEdited] = useState<'all' | 'edited' | 'original'>('all');

  const filteredChunks = chunks.filter(chunk => {
    const matchesSearch = chunk.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         (chunk.section_title?.toLowerCase() || '').includes(searchQuery.toLowerCase());
    
    const matchesFilter = filterEdited === 'all' ? true :
                         filterEdited === 'edited' ? chunk.is_edited :
                         !chunk.is_edited;
    
    return matchesSearch && matchesFilter;
  });

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 bg-white">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">
            Document Chunks ({chunks.length})
          </h2>
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setFilterEdited('all')}
              className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                filterEdited === 'all'
                  ? 'bg-primary-100 text-primary-700'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              All
            </button>
            <button
              onClick={() => setFilterEdited('edited')}
              className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                filterEdited === 'edited'
                  ? 'bg-primary-100 text-primary-700'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              Edited
            </button>
            <button
              onClick={() => setFilterEdited('original')}
              className={`px-3 py-1 text-sm rounded-lg transition-colors ${
                filterEdited === 'original'
                  ? 'bg-primary-100 text-primary-700'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              Original
            </button>
          </div>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search chunks..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
          />
        </div>
      </div>

      {/* Chunk List */}
      <div className="flex-1 overflow-y-auto">
        {filteredChunks.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <FileText className="w-16 h-16 text-gray-300 mb-4" />
            <p className="text-gray-600">
              {searchQuery ? 'No chunks found matching your search' : 'No chunks available'}
            </p>
          </div>
        ) : (
          <div className="p-6 space-y-3">
            {filteredChunks.map((chunk) => (
              <div
                key={chunk.id}
                className="bg-white border border-gray-200 rounded-lg hover:shadow-md transition-shadow"
              >
                <div className="p-4">
                  {/* Chunk Header */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1">
                      <div className="flex items-center space-x-2 mb-1">
                        <h3 className="text-sm font-semibold text-gray-900">
                          Chunk #{chunk.chunk_index + 1}
                        </h3>
                        {chunk.is_edited && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800">
                            <CheckCircle className="w-3 h-3 mr-1" />
                            Edited ({chunk.edit_count}x)
                          </span>
                        )}
                      </div>
                      <div className="flex items-center space-x-3 text-xs text-gray-500">
                        <span>Type: {chunk.chunk_type}</span>
                        <span>Pages: {chunk.page_numbers.join(', ')}</span>
                        {chunk.section_title && (
                          <span>Section: {chunk.section_title}</span>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => onEditChunk(chunk)}
                      className="flex items-center px-3 py-1.5 text-sm font-medium text-primary-700 bg-primary-50 rounded-lg hover:bg-primary-100 transition-colors"
                    >
                      <Edit className="w-4 h-4 mr-1" />
                      {isAdmin ? 'Edit' : 'View'}
                    </button>
                  </div>

                  {/* Chunk Preview */}
                  <div className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                    <p className="text-sm text-gray-700 line-clamp-3">
                      {chunk.content}
                    </p>
                  </div>

                  {/* Chunk Stats */}
                  <div className="mt-3 flex items-center justify-between text-xs text-gray-500">
                    <span>Tokens: {chunk.token_count}</span>
                    <span>Length: {chunk.content.length} chars</span>
                    {chunk.edited_at && (
                      <span>Last edited: {new Date(chunk.edited_at).toLocaleDateString()}</span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}