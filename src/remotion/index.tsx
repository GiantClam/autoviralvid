/**
 * Remotion Root - 注册所有合成配置
 * 本地渲染脚本通过 serveUrl 指向此入口
 */

import type React from 'react';
import { Composition, registerRoot } from 'remotion';
import type { AnyZodObject } from 'remotion';
import SlidePresentation from './compositions/SlidePresentation';
import VideoTemplate from './compositions/VideoTemplate';
import ImageSlideshow from './compositions/ImageSlideshow';
import type { SlidePresentationProps } from './compositions/SlidePresentation';
import type { ImageSlideshowProps } from './compositions/ImageSlideshow';
import type { VideoTemplateProps } from './compositions/VideoTemplate';

const defaultSlides: SlidePresentationProps['slides'] = [];

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* PPT 讲解视频 - Feature B */}
      <Composition<AnyZodObject, SlidePresentationProps>
        id="SlidePresentation"
        component={SlidePresentation}
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
      <Composition<AnyZodObject, VideoTemplateProps>
        id="VideoTemplate"
        component={VideoTemplate}
        durationInFrames={900}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{
          clips: [],
          subtitles: [],
          bgmUrl: undefined,
          bgmVolume: 0.15,
          transition: 'fade' as const,
          style: {
            fontFamily: 'Plus Jakarta Sans, Inter, sans-serif',
          },
          introText: 'AutoViralVid',
          outroText: 'Thanks for watching',
        }}
      />

      {/* 截图幻灯片 - HTML截图 + 音频 -> 视频 */}
      <Composition<AnyZodObject, ImageSlideshowProps>
        id="ImageSlideshow"
        component={ImageSlideshow}
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
