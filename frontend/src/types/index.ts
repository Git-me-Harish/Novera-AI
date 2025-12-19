export interface TokenStats {
  conversation_id: string;
  summary: {
    total_messages: number;
    total_tokens: number;
    cached_tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
    cache_efficiency_percent: number;
    total_cost_usd: number;
    avg_tokens_per_message: number;
    avg_cost_per_message: number;
  };
  messages: MessageTokenStat[];
  pricing_info: {
    model: string;
    cached_token_price: number;
    regular_token_price: number;
    currency: string;
  };
}

export interface MessageTokenStat {
  message_id: string;
  timestamp: string;
  tokens: {
    total: number;
    cached: number;
    prompt: number;
    completion: number;
  };
  cost_usd: number;
}