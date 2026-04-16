'use client';
import { RfqListPage } from '../_shared/RfqListPage';
export default function AllRfqsPage() {
  return (
    <RfqListPage
      title="All RFQs"
      subtitle="Complete history of all your engineering request proposals"
      filter={() => true}
      emptyMessage="You haven't submitted any RFQs yet. Start by submitting your first engineering project request."
      showCancel={false}
    />
  );
}
