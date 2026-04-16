'use client';
import { RfqListPage } from '../_shared/RfqListPage';
export default function AcceptedRfqsPage() {
  return (
    <RfqListPage
      title="Accepted RFQs"
      subtitle="RFQs where you have selected a provider and moved to direct engagement"
      filter={rfq => rfq.rfq_status === 'customer_selected_provider'}
      emptyMessage="You haven't accepted a provider quote yet. Once you select a provider from your quoted RFQs, they will appear here."
      showCancel={false}
    />
  );
}
