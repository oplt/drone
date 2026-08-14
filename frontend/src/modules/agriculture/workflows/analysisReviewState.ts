export const ANALYSIS_OBSERVATION_QUERY = "observation";
export const ANALYSIS_REVIEW_QUERY = "review";
export const ANALYSIS_REVIEW_OPEN = "open";
export const ANALYSIS_REVIEW_EVIDENCE = "evidence";

export function readAnalysisReviewState(searchParams: URLSearchParams) {
  const review = searchParams.get(ANALYSIS_REVIEW_QUERY);
  return {
    observationId: searchParams.get(ANALYSIS_OBSERVATION_QUERY),
    reviewOpen: review === ANALYSIS_REVIEW_OPEN || review === ANALYSIS_REVIEW_EVIDENCE,
    focusEvidence: review === ANALYSIS_REVIEW_EVIDENCE,
  };
}

export function writeObservationSelection(
  searchParams: URLSearchParams,
  observationId: string | null,
  options?: {
    review?: typeof ANALYSIS_REVIEW_OPEN | typeof ANALYSIS_REVIEW_EVIDENCE | false;
  },
): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  if (observationId) {
    next.set(ANALYSIS_OBSERVATION_QUERY, observationId);
  } else {
    next.delete(ANALYSIS_OBSERVATION_QUERY);
  }
  if (options && "review" in options) {
    if (options.review) {
      next.set(ANALYSIS_REVIEW_QUERY, options.review);
    } else {
      next.delete(ANALYSIS_REVIEW_QUERY);
    }
  }
  return next;
}
