interface Counters {
  requests: number;
  prompt_tokens: number;
  completion_tokens: number;
}

export const tokensOf = (counters: Counters): number => counters.prompt_tokens + counters.completion_tokens;
export const requestsOf = (counters: Counters): number => counters.requests;
