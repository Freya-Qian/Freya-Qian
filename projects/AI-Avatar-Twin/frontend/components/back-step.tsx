'use client';

import { useRouter } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';

type BackStepProps = {
  fallbackHref: string;
  label?: string;
};

export function BackStep({ fallbackHref, label = '返回上一步' }: BackStepProps) {
  const router = useRouter();

  const handleBack = () => {
    router.push(fallbackHref);
  };

  return (
    <button className="btn btn-ghost back-step" type="button" onClick={handleBack}>
      <ArrowLeft size={16} /> {label}
    </button>
  );
}
