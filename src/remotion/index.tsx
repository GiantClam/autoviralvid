/**
 * Remotion Root - 注册所有合成配置
 * 本地渲染脚本通过 serveUrl 指向此入口
 */

import type React from 'react';
import { Composition, registerRoot } from 'remotion';
import SlidePresentation from './compositions/SlidePresentation';
import VideoTemplate from './compositions/VideoTemplate';
import ImageSlideshow from './compositions/ImageSlideshow';
import type { SlidePresentationProps } from './compositions/SlidePresentation';
import type { ImageSlideshowProps } from './compositions/ImageSlideshow';

const defaultSlides: SlidePresentationProps['slides'] = [];
const SlidePresentationComponent =
  SlidePresentation as React.ComponentType<SlidePresentationProps>;
const VideoTemplateComponent = VideoTemplate as React.ComponentType;
const ImageSlideshowComponent =
  ImageSlideshow as React.ComponentType<ImageSlideshowProps>;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* PPT 讲解视频 - Feature B */}
      <Composition
        id="SlidePresentation"
        component={SlidePresentationComponent}
        durationInFrames={3600}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          slides: defaultSlides,
          bgmUrl: undefined,
          bgmVolume: 0.15,
          defaultTransition: 'fade' as const,
        }}
      />

      {/* 通用视频模板 */}
      <Composition
        id="VideoTemplate"
        component={VideoTemplateComponent}
        durationInFrames={900}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          clips: [],
          subtitles: [],
          transitionType: 'fade' as const,
          templateStyle: 'modern' as const,
          voiceover: undefined,
          brandName: 'AutoViralVid',
        }}
      />

      {/* 截图幻灯片 - HTML截图 + 音频 -> 视频 */}
      <Composition
        id="ImageSlideshow"
        component={ImageSlideshowComponent}
        durationInFrames={3600}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          slides: [],
        } as ImageSlideshowProps}
      />
    </>
  );
};

export default RemotionRoot;

registerRoot(RemotionRoot);
