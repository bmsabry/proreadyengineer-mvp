'use client';
import { RfqListPage } from '../_shared/RfqListPage';
export default function QuotedRfqsPage() {
  return (
    <RfqListPage
      title="Quoted RFQs"
      subtitle="RFQs that have received at least one provider quote"
      filter={rfq => rfq.quote_count > 0}
      emptyMessage="None of your RFQs have received quotes yet. Active RFQs will appear here once providers submit quotes."
      showCancel={false}
    />
  );
}
