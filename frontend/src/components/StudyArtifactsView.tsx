import { useState } from 'react';
import { Check, X, HelpCircle, BookOpen, Layers } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { StudyArtifacts } from '@/api';

interface StudyArtifactsViewProps {
  artifacts: StudyArtifacts;
}

export function StudyArtifactsView({ artifacts }: StudyArtifactsViewProps) {
  const [activeTab, setActiveTab] = useState<'questions' | 'flashcards' | 'quiz'>('questions');
  const [revealedAnswers, setRevealedAnswers] = useState<Record<number, boolean>>({});
  const [quizAnswers, setQuizAnswers] = useState<Record<number, number>>({});
  const [quizSubmitted, setQuizSubmitted] = useState<Record<number, boolean>>({});

  const toggleRevealAnswer = (index: number) => {
    setRevealedAnswers((prev) => ({ ...prev, [index]: !prev[index] }));
  };

  const handleSelectQuizOption = (questionIndex: number, optionIndex: number) => {
    if (quizSubmitted[questionIndex]) return;
    setQuizAnswers((prev) => ({ ...prev, [questionIndex]: optionIndex }));
  };

  const handleSubmitQuizAnswer = (questionIndex: number) => {
    if (quizAnswers[questionIndex] === undefined) return;
    setQuizSubmitted((prev) => ({ ...prev, [questionIndex]: true }));
  };

  return (
    <div className="space-y-4 rounded-lg border border-border bg-background p-4 mt-6">
      <div className="flex border-b border-border">
        <button
          onClick={() => setActiveTab('questions')}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-[2px] transition-colors cursor-pointer ${
            activeTab === 'questions'
              ? 'border-primary text-primary font-semibold'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <HelpCircle className="size-4" />
          Comprehension
        </button>
        <button
          onClick={() => setActiveTab('flashcards')}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-[2px] transition-colors cursor-pointer ${
            activeTab === 'flashcards'
              ? 'border-primary text-primary font-semibold'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <Layers className="size-4" />
          Flashcards
        </button>
        <button
          onClick={() => setActiveTab('quiz')}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 -mb-[2px] transition-colors cursor-pointer ${
            activeTab === 'quiz'
              ? 'border-primary text-primary font-semibold'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <BookOpen className="size-4" />
          Quiz
        </button>
      </div>

      <div className="py-2">
        {activeTab === 'questions' && (
          <div className="space-y-4">
            {artifacts.comprehension_questions.map((item, index) => (
              <div
                key={index}
                className="rounded-md border border-border p-4 bg-muted/10 space-y-3"
              >
                <div className="text-sm font-medium text-foreground">
                  Q{index + 1}: {item.question}
                </div>
                {revealedAnswers[index] ? (
                  <div className="text-sm bg-muted/40 p-3 rounded text-muted-foreground border-l-2 border-primary">
                    <div className="font-semibold text-xs text-foreground mb-1">
                      Expected Answer:
                    </div>
                    {item.expected_answer}
                  </div>
                ) : null}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => toggleRevealAnswer(index)}
                  className="w-full sm:w-auto"
                >
                  {revealedAnswers[index] ? 'Hide Answer' : 'Show Answer'}
                </Button>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'flashcards' && (
          <div className="grid gap-4 sm:grid-cols-2">
            {artifacts.flashcards.map((item, index) => (
              <div
                key={index}
                onClick={() => toggleRevealAnswer(index + 100)}
                className="group relative cursor-pointer min-h-[140px] rounded-lg border border-border p-5 flex flex-col justify-between transition-all hover:shadow-sm hover:border-primary bg-muted/15"
              >
                <div>
                  <Badge variant="outline" className="mb-2 uppercase text-[10px]">
                    {item.concept}
                  </Badge>
                  <p className="text-sm text-foreground leading-relaxed">
                    {revealedAnswers[index + 100]
                      ? item.claim
                      : 'Click to flip and reveal details...'}
                  </p>
                </div>
                <div className="text-[10px] text-muted-foreground mt-4 group-hover:text-primary transition-colors">
                  {revealedAnswers[index + 100] ? 'Click to hide details' : 'Click to show details'}
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'quiz' && (
          <div className="space-y-6">
            {artifacts.quiz.map((item, qIdx) => {
              const selectedOpt = quizAnswers[qIdx];
              const isSubmitted = quizSubmitted[qIdx];
              return (
                <div
                  key={qIdx}
                  className="rounded-md border border-border p-4 bg-muted/5 space-y-4"
                >
                  <div className="text-sm font-semibold text-foreground">
                    Question {qIdx + 1}: {item.question}
                  </div>
                  <div className="grid gap-2">
                    {item.options.map((option, oIdx) => {
                      const isSelected = selectedOpt === oIdx;
                      const isCorrect = item.correct_index === oIdx;
                      let optionStyle = 'border-border bg-background hover:bg-muted/30';
                      if (isSelected) {
                        optionStyle = 'border-primary bg-primary/5';
                      }
                      if (isSubmitted) {
                        if (isCorrect) {
                          optionStyle =
                            'border-green-500 bg-green-500/10 text-green-700 dark:text-green-400';
                        } else if (isSelected) {
                          optionStyle =
                            'border-red-500 bg-red-500/10 text-red-700 dark:text-red-400';
                        }
                      }
                      return (
                        <button
                          key={oIdx}
                          onClick={() => handleSelectQuizOption(qIdx, oIdx)}
                          disabled={isSubmitted}
                          className={`w-full text-left px-4 py-3 rounded-md border text-sm flex items-center justify-between transition-colors ${
                            !isSubmitted ? 'cursor-pointer' : 'cursor-not-allowed'
                          } ${optionStyle}`}
                        >
                          <span>{option}</span>
                          {isSubmitted && isCorrect ? (
                            <Check className="size-4 text-green-600 shrink-0" />
                          ) : null}
                          {isSubmitted && isSelected && !isCorrect ? (
                            <X className="size-4 text-red-600 shrink-0" />
                          ) : null}
                        </button>
                      );
                    })}
                  </div>

                  {!isSubmitted ? (
                    <Button
                      onClick={() => handleSubmitQuizAnswer(qIdx)}
                      disabled={selectedOpt === undefined}
                      className="w-full sm:w-auto"
                    >
                      Submit Answer
                    </Button>
                  ) : (
                    <div className="text-xs bg-muted/40 p-3 rounded text-muted-foreground border-l-2 border-blue-500">
                      <div className="font-semibold text-[10px] uppercase text-foreground mb-1">
                        Feedback:
                      </div>
                      {item.explanation}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
