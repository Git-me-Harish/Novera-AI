import { FileText, Clock, X, Sparkles, ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';

interface ContextIndicatorProps {
  contextSummary?: {
    primary_document?: string;
    active_documents?: string[];
    recent_time_period?: string;
    message_count?: number;
  };
  onClearContext?: () => void;
}

export default function ContextIndicator({ contextSummary, onClearContext }: ContextIndicatorProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!contextSummary || (!contextSummary.primary_document && !contextSummary.recent_time_period)) {
    return null;
  }

  const hasContext = contextSummary.primary_document || contextSummary.recent_time_period;

  return (
    <div className="mb-3 sm:mb-4 px-3 sm:px-0">
      <div className="max-w-4xl mx-auto">
        {/* Compact Context Bar */}
        <div className="bg-gradient-to-r from-blue-50 to-purple-50 border border-blue-200 rounded-lg p-2.5 sm:p-3 shadow-sm">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-start gap-2 sm:gap-3 flex-1 min-w-0">
              <div className="flex items-center justify-center w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-blue-100 flex-shrink-0">
                <Sparkles className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-blue-600" />
              </div>
              
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                  {contextSummary.primary_document && (
                    <div className="flex items-center gap-1 sm:gap-1.5 px-2 py-1 bg-white rounded-md border border-blue-200 shadow-sm max-w-full">
                      <FileText className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-blue-600 flex-shrink-0" />
                      <span className="text-xs font-medium text-gray-700 truncate">
                        {contextSummary.primary_document}
                      </span>
                    </div>
                  )}
                  
                  {contextSummary.recent_time_period && (
                    <div className="flex items-center gap-1 sm:gap-1.5 px-2 py-1 bg-white rounded-md border border-purple-200 shadow-sm">
                      <Clock className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-purple-600 flex-shrink-0" />
                      <span className="text-xs font-medium text-gray-700 whitespace-nowrap">
                        {contextSummary.recent_time_period}
                      </span>
                    </div>
                  )}
                  
                  {contextSummary.active_documents && contextSummary.active_documents.length > 1 && (
                    <button
                      onClick={() => setIsExpanded(!isExpanded)}
                      className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-blue-600 hover:text-blue-700 hover:bg-white rounded-md transition-colors min-touch-target"
                    >
                      <span>+{contextSummary.active_documents.length - 1} more</span>
                      {isExpanded ? (
                        <ChevronUp className="w-3 h-3" />
                      ) : (
                        <ChevronDown className="w-3 h-3" />
                      )}
                    </button>
                  )}
                </div>
                
                <p className="text-xs text-gray-500 mt-1 hidden sm:block">
                  I'm focusing on this context for your questions
                </p>
              </div>
            </div>

            {onClearContext && (
              <button
                onClick={onClearContext}
                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-white rounded-md transition-colors flex-shrink-0 min-touch-target"
                title="Clear context"
                aria-label="Clear context"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Expanded View - Mobile Optimized */}
          {isExpanded && contextSummary.active_documents && contextSummary.active_documents.length > 1 && (
            <div className="mt-3 pt-3 border-t border-blue-200 animate-slideUp">
              <p className="text-xs font-medium text-gray-600 mb-2">Active Documents:</p>
              <div className="space-y-1.5">
                {contextSummary.active_documents.map((doc, idx) => (
                  <div
                    key={idx}
                    className="flex items-center gap-2 px-2 sm:px-2.5 py-1.5 bg-white rounded border border-gray-200 text-xs text-gray-700"
                  >
                    <FileText className="w-3 h-3 text-gray-400 flex-shrink-0" />
                    <span className="truncate flex-1">{doc}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}