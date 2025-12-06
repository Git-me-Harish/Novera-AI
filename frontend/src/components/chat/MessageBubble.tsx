import { User, Bot } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChatMessage } from '../../services/api';

interface MessageBubbleProps {
  message: ChatMessage;
}

export default function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex items-start gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      {!isUser ? (
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center flex-shrink-0 shadow-md">
          <Bot className="w-5 h-5 text-white" />
        </div>
      ) : (
        <div className="w-8 h-8 rounded-full bg-gray-300 flex items-center justify-center flex-shrink-0">
          <User className="w-5 h-5 text-gray-600" />
        </div>
      )}

      {/* Message Content */}
      <div className={`flex-1 max-w-3xl ${isUser ? 'flex justify-end' : ''}`}>
        <div
          className={`rounded-2xl px-4 py-3 ${
            isUser
              ? 'bg-gradient-to-r from-blue-600 to-blue-500 text-white shadow-md'
              : 'bg-white border border-gray-200 shadow-sm'
          }`}
        >
          {isUser ? (
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="prose prose-sm max-w-none prose-headings:font-semibold prose-headings:text-gray-900 prose-p:text-gray-700 prose-p:leading-relaxed prose-a:text-blue-600 prose-a:no-underline hover:prose-a:underline prose-strong:text-gray-900 prose-strong:font-semibold prose-code:text-pink-600 prose-code:bg-pink-50 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:before:content-[''] prose-code:after:content-[''] prose-pre:bg-gray-900 prose-pre:text-gray-100 prose-ul:list-disc prose-ul:pl-4 prose-ol:list-decimal prose-ol:pl-4 prose-li:text-gray-700 prose-li:my-1 prose-blockquote:border-l-4 prose-blockquote:border-blue-500 prose-blockquote:pl-4 prose-blockquote:italic prose-blockquote:text-gray-600">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  // Custom rendering for better formatting
                  h1: ({ node, ...props }) => (
                    <h1 className="text-xl font-bold text-gray-900 mt-4 mb-2" {...props} />
                  ),
                  h2: ({ node, ...props }) => (
                    <h2 className="text-lg font-semibold text-gray-900 mt-3 mb-2" {...props} />
                  ),
                  h3: ({ node, ...props }) => (
                    <h3 className="text-base font-semibold text-gray-900 mt-2 mb-1" {...props} />
                  ),
                  p: ({ node, ...props }) => (
                    <p className="text-gray-700 leading-relaxed my-2" {...props} />
                  ),
                  ul: ({ node, ...props }) => (
                    <ul className="list-disc pl-5 my-2 space-y-1" {...props} />
                  ),
                  ol: ({ node, ...props }) => (
                    <ol className="list-decimal pl-5 my-2 space-y-1" {...props} />
                  ),
                  li: ({ node, ...props }) => (
                    <li className="text-gray-700 leading-relaxed" {...props} />
                  ),
                  blockquote: ({ node, ...props }) => (
                    <blockquote className="border-l-4 border-blue-500 pl-4 italic text-gray-600 my-3" {...props} />
                  ),
                  code: ({ node, inline, ...props }: any) =>
                    inline ? (
                      <code className="bg-pink-50 text-pink-600 px-1.5 py-0.5 rounded text-sm font-mono" {...props} />
                    ) : (
                      <code className="block bg-gray-900 text-gray-100 p-3 rounded-lg overflow-x-auto text-sm font-mono my-2" {...props} />
                    ),
                  a: ({ node, ...props }) => (
                    <a className="text-blue-600 hover:text-blue-700 hover:underline" target="_blank" rel="noopener noreferrer" {...props} />
                  ),
                  table: ({ node, ...props }) => (
                    <div className="overflow-x-auto my-3">
                      <table className="min-w-full divide-y divide-gray-300 border border-gray-300" {...props} />
                    </div>
                  ),
                  th: ({ node, ...props }) => (
                    <th className="px-3 py-2 bg-gray-100 text-left text-sm font-semibold text-gray-900 border-b border-gray-300" {...props} />
                  ),
                  td: ({ node, ...props }) => (
                    <td className="px-3 py-2 text-sm text-gray-700 border-b border-gray-200" {...props} />
                  ),
                  hr: ({ node, ...props }) => (
                    <hr className="my-4 border-gray-300" {...props} />
                  ),
                }}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          )}

          {/* Metadata for assistant messages */}
          {!isUser && message.metadata && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              {message.metadata.confidence && (
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-gray-500">Confidence:</span>
                  <span
                    className={`px-2 py-0.5 rounded-full font-medium ${
                      message.metadata.confidence === 'high'
                        ? 'bg-green-100 text-green-700'
                        : message.metadata.confidence === 'medium'
                        ? 'bg-yellow-100 text-yellow-700'
                        : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {message.metadata.confidence}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Timestamp */}
        {message.timestamp && (
          <p className={`text-xs text-gray-400 mt-1 ${isUser ? 'text-right' : 'text-left'}`}>
            {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </p>
        )}
      </div>
    </div>
  );
}