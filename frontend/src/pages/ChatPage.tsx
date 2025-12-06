import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Send, Loader2, FileText, AlertCircle, Plus, Sparkles } from 'lucide-react';
import api, { ChatMessage, ChatResponse, Source } from '../services/api';
import MessageBubble from '../components/chat/MessageBubble';
import SourceCard from '../components/chat/SourceCard';

export default function ChatPage() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(
    conversationId || null
  );
  const [sources, setSources] = useState<Source[]>([]);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Load conversation if ID provided
  useEffect(() => {
    if (conversationId) {
      loadConversation(conversationId);
    }
  }, [conversationId]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
      inputRef.current.style.height = `${Math.min(inputRef.current.scrollHeight, 120)}px`;
    }
  }, [input]);

  const loadConversation = async (convId: string) => {
    try {
      const conversation = await api.getConversation(convId);
      setMessages(conversation.messages);
      setCurrentConversationId(convId);
    } catch (err) {
      console.error('Failed to load conversation:', err);
      setError('Failed to load conversation');
    }
  };

  const handleSendMessage = async () => {
    if (!input.trim() || loading) return;

    const userMessage: ChatMessage = {
      role: 'user',
      content: input.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    setError(null);

    try {
      const response: ChatResponse = await api.sendChatMessage({
        query: input.trim(),
        conversation_id: currentConversationId,
      });

      // Update conversation ID if new
      if (!currentConversationId && response.conversation_id) {
        setCurrentConversationId(response.conversation_id);
        navigate(`/chat/${response.conversation_id}`, { replace: true });
      }

      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: response.answer,
        timestamp: new Date().toISOString(),
        metadata: {
          sources: response.sources,
          confidence: response.confidence,
          citations: response.citations,
        },
      };

      setMessages((prev) => [...prev, assistantMessage]);
      setSources(response.sources);
      setError(null);

    } catch (err: any) {
      console.error('Chat error:', err);
      const errorMessage = err.response?.data?.detail || 'Failed to send message. Please try again.';
      
      // Show error as assistant message
      const errorAssistantMessage: ChatMessage = {
        role: 'assistant',
        content: `I apologize, but I encountered an error: ${errorMessage}\n\nPlease try rephrasing your question or try again in a moment.`,
        timestamp: new Date().toISOString(),
        metadata: { error: true },
      };
      
      setMessages((prev) => [...prev, errorAssistantMessage]);
    } finally {
      setLoading(false);
      // Focus back to input
      inputRef.current?.focus();
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const startNewChat = () => {
    setMessages([]);
    setCurrentConversationId(null);
    setSources([]);
    setError(null);
    navigate('/chat');
    inputRef.current?.focus();
  };

  const exampleQuestions = [
    'What is this document about?',
    'Explain the leave policy',
    'Show me expense reimbursement details',
    'What was the Q4 revenue?',
  ];

  return (
    <div className="flex h-full bg-gray-50">
      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <div className="h-16 border-b border-gray-200 bg-white px-6 flex items-center justify-between shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-md">
              <Sparkles className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-gray-900">
                {currentConversationId ? 'Chat with Mentanova' : 'New Conversation'}
              </h1>
              <p className="text-xs text-gray-500">AI-powered document assistant</p>
            </div>
          </div>
          {messages.length > 0 && (
            <button
              onClick={startNewChat}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
            >
              <Plus className="w-4 h-4" />
              New Chat
            </button>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">
            {messages.length === 0 && (
              <div className="h-full flex items-center justify-center py-12">
                <div className="text-center max-w-2xl">
                  <div className="w-20 h-20 bg-gradient-to-br from-blue-100 to-purple-100 rounded-2xl mx-auto mb-6 flex items-center justify-center shadow-lg">
                    <Sparkles className="w-10 h-10 text-blue-600" />
                  </div>
                  <h2 className="text-2xl font-bold text-gray-900 mb-3">
                    Welcome to Mentanova AI
                  </h2>
                  <p className="text-gray-600 mb-8 leading-relaxed">
                    I'm your AI assistant specialized in Finance and HRMS documents. Ask me anything about your uploaded documents, policies, or just have a conversation!
                  </p>
                  
                  <div className="space-y-3">
                    <p className="text-sm font-medium text-gray-700">Try asking:</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {exampleQuestions.map((example, idx) => (
                        <button
                          key={idx}
                          onClick={() => setInput(example)}
                          className="px-4 py-3 text-sm text-left text-gray-700 bg-white hover:bg-gray-50 border border-gray-200 hover:border-blue-300 rounded-lg transition-all shadow-sm hover:shadow"
                        >
                          <FileText className="w-4 h-4 inline mr-2 text-gray-400" />
                          {example}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {messages.map((message, index) => (
              <MessageBubble key={index} message={message} />
            ))}

            {loading && (
              <div className="flex items-start gap-3">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center flex-shrink-0 shadow-md">
                  <Sparkles className="w-5 h-5 text-white" />
                </div>
                <div className="flex-1 bg-white rounded-2xl p-4 shadow-sm border border-gray-200">
                  <div className="flex items-center gap-3 text-gray-500">
                    <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
                    <div className="flex gap-1">
                      <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                      <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                      <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input */}
        <div className="border-t border-gray-200 bg-white p-4 shadow-lg">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-end gap-2">
              <div className="flex-1 relative">
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Ask me anything about your documents..."
                  rows={1}
                  className="w-full px-4 py-3 pr-12 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none shadow-sm"
                  style={{ minHeight: '48px', maxHeight: '120px' }}
                  disabled={loading}
                />
              </div>
              <button
                onClick={handleSendMessage}
                disabled={!input.trim() || loading}
                className="px-4 py-3 bg-gradient-to-r from-blue-600 to-blue-500 text-white rounded-xl hover:from-blue-700 hover:to-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-md hover:shadow-lg disabled:shadow-none"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
            <p className="mt-2 text-xs text-gray-500 text-center">
              Press Enter to send • Shift+Enter for new line
            </p>
          </div>
        </div>
      </div>

      {/* Sources Sidebar */}
      {sources.length > 0 && (
        <div className="w-80 border-l border-gray-200 bg-white overflow-y-auto">
          <div className="p-4 border-b border-gray-200 bg-gray-50">
            <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
              <FileText className="w-4 h-4 text-blue-600" />
              Sources ({sources.length})
            </h3>
          </div>
          <div className="p-4 space-y-2">
            {sources.map((source, index) => (
              <SourceCard key={index} source={source} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}