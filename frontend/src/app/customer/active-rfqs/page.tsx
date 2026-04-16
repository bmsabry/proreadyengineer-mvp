'use client';
import { RfqListPage, ACTIVE_STATUSES } from '../_shared/RfqListPage';
export default function ActiveRfqsPage() {
  return (
    <RfqListPage
      title="Active RFQs"
      subtitle="RFQs currently open and awaiting provider quotes"
      filter={rfq => ACTIVE_STATUSES.includes(rfq.rfq_status)}
      emptyMessage="You have no active RFQs right now. Submit a new one to get quotes from qualified engineering firms."
      showCancel={true}
    />
  );
}
