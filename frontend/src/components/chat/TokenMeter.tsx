import React, { useEffect, useState } from 'react';
import api from '../../services/api';
import type { TokenStats } from '../../services/api';

interface TokenMeterProps {
  conversationId: string | null;
  isVisible?: boolean;
}

const TokenMeter: React.FC<TokenMeterProps> = ({ 
  conversationId, 
  isVisible = true 
}) => {
  const [stats, setStats] = useState<TokenStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!conversationId || !isVisible) {
      setStats(null);
      return;
    }

    const fetchStats = async () => {
      setLoading(true);
      setError(null);
      
      try {
        const data = await api.getConversationTokenStats(conversationId);
        setStats(data);
      } catch (err: any) {
        console.error('Failed to fetch token stats:', err);
        setError(err.message || 'Failed to load token stats');
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
    
    const interval = setInterval(fetchStats, 10000);
    
    return () => clearInterval(interval);
  }, [conversationId, isVisible]);

  if (!isVisible || !conversationId) return null;

  if (loading && !stats) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
        <div className="text-sm text-gray-500">Loading token stats...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-3">
        <div className="text-sm text-red-600">Error: {error}</div>
      </div>
    );
  }

  if (!stats) return null;

  const { summary } = stats;
  const cacheEfficiencyColor = 
    summary.cache_efficiency_percent > 70 ? 'text-green-600' :
    summary.cache_efficiency_percent > 40 ? 'text-yellow-600' :
    'text-red-600';

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
          Token Usage & Cost
        </h3>
      </div>

      <div className="p-4 space-y-3">
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-blue-900">Total Cost</span>
            <span className="text-2xl font-bold text-blue-600">
              ${summary.total_cost_usd.toFixed(6)}
            </span>
          </div>
          <div className="text-xs text-blue-700 mt-1">
            {summary.total_messages} messages • Avg: ${summary.avg_cost_per_message.toFixed(6)}/msg
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div className="bg-gray-50 rounded p-2">
            <div className="text-xs text-gray-500">Total Tokens</div>
            <div className="text-lg font-semibold text-gray-900">
              {summary.total_tokens.toLocaleString()}
            </div>
          </div>
          
          <div className="bg-green-50 rounded p-2">
            <div className="text-xs text-green-700">Cached Tokens</div>
            <div className="text-lg font-semibold text-green-600">
              {summary.cached_tokens.toLocaleString()}
            </div>
          </div>
        </div>

        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-600">Cache Efficiency</span>
            <span className={`font-semibold ${cacheEfficiencyColor}`}>
              {summary.cache_efficiency_percent.toFixed(1)}%
            </span>
          </div>
          
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div 
              className={`h-2 rounded-full transition-all ${
                summary.cache_efficiency_percent > 70 ? 'bg-green-500' :
                summary.cache_efficiency_percent > 40 ? 'bg-yellow-500' :
                'bg-red-500'
              }`}
              style={{ width: `${summary.cache_efficiency_percent}%` }}
            />
          </div>
        </div>

        <details className="text-xs">
          <summary className="cursor-pointer text-gray-600 hover:text-gray-900 font-medium">
            View Details
          </summary>
          <div className="mt-2 space-y-1 pl-2 border-l-2 border-gray-200">
            <div className="flex justify-between">
              <span className="text-gray-500">Prompt Tokens:</span>
              <span className="font-mono">{summary.prompt_tokens.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Completion Tokens:</span>
              <span className="font-mono">{summary.completion_tokens.toLocaleString()}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Model:</span>
              <span className="font-mono text-blue-600">{stats.pricing_info.model}</span>
            </div>
          </div>
        </details>

        <div className="text-xs text-gray-500 pt-2 border-t border-gray-200">
          <div className="flex justify-between">
            <span>Regular tokens cost:</span>
            <span className="font-mono">
              ${((summary.total_tokens - summary.cached_tokens) * stats.pricing_info.regular_token_price).toFixed(6)}
            </span>
          </div>
          <div className="flex justify-between text-green-600">
            <span>Cached tokens cost:</span>
            <span className="font-mono">
              ${(summary.cached_tokens * stats.pricing_info.cached_token_price).toFixed(6)}
            </span>
          </div>
          <div className="flex justify-between font-semibold text-gray-700 mt-1 pt-1 border-t border-gray-300">
            <span>Savings from cache:</span>
            <span className="font-mono text-green-600">
              ${((summary.cached_tokens * (stats.pricing_info.regular_token_price - stats.pricing_info.cached_token_price))).toFixed(6)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TokenMeter;