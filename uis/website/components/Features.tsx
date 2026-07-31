interface FeatureCardProps {
  icon: string;
  title: string;
  description: string;
}

function FeatureCard({ icon, title, description }: FeatureCardProps) {
  return (
    <article className="rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
      <div className="mb-4 text-3xl" aria-hidden="true">
        {icon}
      </div>
      <h3 className="mb-2 text-lg font-semibold text-stone-900">{title}</h3>
      <p className="text-sm text-stone-600 leading-relaxed">{description}</p>
    </article>
  );
}

export default function Features() {
  const features: FeatureCardProps[] = [
    {
      icon: "🔥",
      title: "Consistent quality",
      description:
        "A Brasaland picanha is prepared and presented the same way at every location — same cut, same coal, same standard, whether you're in Medellín or Miami Beach.",
    },
    {
      icon: "🤝",
      title: "Warm service",
      description:
        "We built this business on hospitality. Every team member is trained to deliver the same warm, attentive service experience that our first guests came back for.",
    },
    {
      icon: "⚡",
      title: "Fast kitchen",
      description:
        "Speed without shortcuts. Our kitchen processes are designed to move fast at peak hours — so guests get great food without the wait.",
    },
    {
      icon: "📍",
      title: "14 locations",
      description:
        "From Medellín Centro to Miami Beach: 14 company-owned restaurants, each one managed to the same standard, none of them franchised.",
    },
    {
      icon: "🌎",
      title: "Two markets",
      description:
        "We operate simultaneously in Colombia and Florida — two currencies, two regulatory environments, one brand. What works in Medellín is built to work in Miami.",
    },
    {
      icon: "⭐",
      title: "Brasa Points",
      description:
        "Our loyalty programme rewards returning guests. Going digital means better rewards, less friction, and real data on what our customers love.",
    },
  ];

  return (
    <section
      id="features"
      className="py-20 px-6 bg-stone-50"
      aria-labelledby="features-heading"
    >
      <div className="mx-auto max-w-6xl">
        <div className="mb-12 text-center">
          <h2
            id="features-heading"
            className="mb-4 text-3xl font-bold text-stone-900"
          >
            What Brasaland stands for
          </h2>
          <p className="mx-auto max-w-2xl text-stone-600">
            Three commitments built this business. They are also what drive
            every decision we make as we grow.
          </p>
        </div>
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <FeatureCard key={f.title} {...f} />
          ))}
        </div>
      </div>
    </section>
  );
}
