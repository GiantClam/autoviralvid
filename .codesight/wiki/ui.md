# UI

> **Navigation aid.** Component inventory and prop signatures extracted via AST. Read the source files before adding props or modifying component logic.

**75 components** (react)

## Client Components

- **Error** — props: error, reset — `src\app\error.tsx`
- **GlobalError** — props: error, reset — `src\app\global-error.tsx`
- **NotFound** — `src\app\not-found.tsx`
- **Home** — `src\app\page.tsx`
- **PPTPromptPage** — `src\app\ppt\page.tsx`
- **ProjectsPage** — `src\app\projects\page.tsx`
- **ResetPasswordPage** — `src\app\reset-password\page.tsx`
- **SettingsPage** — `src\app\settings\page.tsx`
- **AIAssistant** — `src\components\AIAssistant.tsx`
- **BatchPanel** — props: templateId, theme, style, duration, orientation, aspectRatio, onClose — `src\components\BatchPanel.tsx`
- **ClipManager** — `src\components\ClipManager.tsx`
- **LandingPage** — `src\components\LandingPage.tsx`
- **LanguageSwitcher** — props: className — `src\components\LanguageSwitcher.tsx`
- **OutlineEditor** — props: outline, onChange, onConfirm, onBack — `src\components\OutlineEditor.tsx`
- **PPTPreview** — props: slides, controlledIndex, onIndexChange — `src\components\PPTPreview.tsx`
- **PricingModal** — props: isOpen, onClose, currentPlan, quotaUsed, quotaTotal — `src\components\PricingModal.tsx`
- **ProgressPanel** — props: compact — `src\components\ProgressPanel.tsx`
- **ProjectForm** — props: onTemplateChange, initialTemplateId, onPptV7StateChange, pptV7RetryToken — `src\components\ProjectForm.tsx`
- **Providers** — `src\components\Providers.tsx`
- **QuotaBar** — props: onUpgrade — `src\components\QuotaBar.tsx`
- **RemotionPreview** — `src\components\RemotionPreview.tsx`
- **RenderProgress** — props: jobId, pollInterval, onComplete, onError — `src\components\RenderProgress.tsx`
- **SocialPanel** — `src\components\SocialPanel.tsx`
- **StoryboardPanel** — `src\components\StoryboardPanel.tsx`
- **TemplateGallery** — props: onSelect — `src\components\TemplateGallery.tsx`
- **EditorProvider** — `src\contexts\EditorContext.tsx`
- **ProjectProvider** — `src\contexts\ProjectContext.tsx`
- **LocaleProvider** — `src\lib\i18n\context.tsx`

## Components

- **RootLayout** — `src\app\layout.tsx`
- **PrivacyPolicy** — `src\app\legal\privacy\page.tsx`
- **TermsOfService** — `src\app\legal\terms\page.tsx`
- **MoonCard** — props: themeColor, status, respond — `src\components\moon.tsx`
- **ProcessGuide** — props: onClose, className — `src\components\ProcessGuide.tsx`
- **AssetLibrary** — `src\components\VideoEditor\AssetLibrary.tsx`
- **EditorPanel** — `src\components\VideoEditor\EditorPanel.tsx`
- **Player** — `src\components\VideoEditor\Player.tsx`
- **PropertyEditor** — `src\components\VideoEditor\PropertyEditor.tsx`
- **SCALE** — `src\components\VideoEditor\Timeline.tsx`
- **WeatherCard** — props: location, themeColor — `src\components\weather.tsx`
- **DrawCircleAction** — props: width, height — `src\remotion\components\ActionEngine.tsx`
- **SpotlightAction** — `src\remotion\components\ActionEngine.tsx`
- **UnderlineAction** — props: width — `src\remotion\components\ActionEngine.tsx`
- **SubtitleBar** — props: role, text — `src\remotion\components\ActionEngine.tsx`
- **ScriptPlayer** — props: script, segments, visualContent — `src\remotion\components\ActionEngine.tsx`
- **ZoomIn** — props: speed — `src\remotion\components\Animations.tsx`
- **PanLeft** — props: distance — `src\remotion\components\Animations.tsx`
- **PanRight** — props: distance — `src\remotion\components\Animations.tsx`
- **Static** — `src\remotion\components\Animations.tsx`
- **MarpSlide** — props: markdown, theme — `src\remotion\components\MarpSlide.tsx`
- **HeroSlide** — props: data — `src\remotion\components\PremiumSlides.tsx`
- **PointsSlide** — props: data — `src\remotion\components\PremiumSlides.tsx`
- **StatsSlide** — props: data — `src\remotion\components\PremiumSlides.tsx`
- **QuoteSlide** — props: data — `src\remotion\components\PremiumSlides.tsx`
- **VersusSlide** — props: data — `src\remotion\components\PremiumSlides.tsx`
- **ClosingSlide** — props: data — `src\remotion\components\PremiumSlides.tsx`
- **PremiumSlideRenderer** — props: data — `src\remotion\components\PremiumSlides.tsx`
- **CoverLayout** — props: content — `src\remotion\components\SlideLayouts.tsx`
- **BulletPointsLayout** — props: content, emphasisWords — `src\remotion\components\SlideLayouts.tsx`
- **ComparisonLayout** — props: content, emphasisWords — `src\remotion\components\SlideLayouts.tsx`
- **QuoteLayout** — props: content, emphasisWords — `src\remotion\components\SlideLayouts.tsx`
- **BigNumberLayout** — props: content — `src\remotion\components\SlideLayouts.tsx`
- **SplitImageLayout** — props: content, emphasisWords, imagePos — `src\remotion\components\SlideLayouts.tsx`
- **SlideLayoutRenderer** — props: slide — `src\remotion\components\SlideLayouts.tsx`
- **ImageSlideshow** — props: slides — `src\remotion\compositions\ImageSlideshow.tsx`
- **KeywordPulse** — props: slides — `src\remotion\compositions\MarpPresentation.tsx`
- **SlidePresentation** — props: slides, bgmUrl, bgmVolume, defaultTransition — `src\remotion\compositions\SlidePresentation.tsx`
- **BeautyReview** — `src\remotion\compositions\templates\BeautyReview.tsx`
- **BrandStory** — `src\remotion\compositions\templates\BrandStory.tsx`
- **FoodShowcase** — `src\remotion\compositions\templates\FoodShowcase.tsx`
- **KnowledgeEdu** — `src\remotion\compositions\templates\KnowledgeEdu.tsx`
- **ProductShowcase** — `src\remotion\compositions\templates\ProductShowcase.tsx`
- **TechUnbox** — `src\remotion\compositions\templates\TechUnbox.tsx`
- **Tutorial** — props: clips, subtitles, steps, totalSteps, bgmUrl, bgmVolume, style, introText, outroText — `src\remotion\compositions\templates\Tutorial.tsx`
- **VideoTemplate** — props: clips, subtitles, bgmUrl, bgmVolume, transition, style, introText, outroText — `src\remotion\compositions\VideoTemplate.tsx`
- **RemotionRoot** — `src\remotion\index.tsx`

---
_Back to [overview.md](./overview.md)_