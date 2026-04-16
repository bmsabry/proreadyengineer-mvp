'use client';
import { RfqListPage } from '../_shared/RfqListPage';
export default function CancelledRfqsPage() {
  return (
    <RfqListPage
      title="Canceled RFQs"
      subtitle="RFQs that were cancelled before provider selection"
      filter={rfq => rfq.rfq_status === 'cancelled'}
      emptyMessage="You have no cancelled RFQs. Cancelled RFQs will appear here."
      showCancel={false}
    />
  );
}
